"""Rebuild a run's supervisor state from RECORDS (BUILD_SPEC §9.3, §11.3, COMMIT-02). Seat 1/3.

Nothing here trusts memory: manifest, grants, revisions, status and policy come from the
repository; step count, observed history, reviews, commitments and corrections come from
the event chain. The result is a `RunRecord` a fresh `SubjectRuntime` can `resume()`
under a new subject session. Reads happen through the repository's public API only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..boundary.canonical import proposal_digest
from ..contracts import (
    ActionDecision,
    ActionProposal,
    Actor,
    Commitment,
    CommitmentKind,
    CommitmentStatus,
    Correction,
    DisclosureLabel,
    EventType,
    GateDecision,
    GateOutcome,
    GateReason,
    ReviewRequest,
    ReviewStatus,
    RunStatus,
    StoredEvent,
    StrictParseError,
    TaskSpec,
    TerminalReason,
    parse_decision,
)
from ..errors import ErrorCode, PebError
from .commitments import CommitmentLedger
from .state import HeldProposal, RunRecord


def _dt(v: str) -> datetime:
    return datetime.fromisoformat(v)


def reconstruct_run(repo: Any, run_id: str, task: TaskSpec) -> tuple[RunRecord, CommitmentLedger]:
    """Rebuild RunRecord + CommitmentLedger for `run_id`. `task` is the public TaskSpec re-loaded from
    the fixture registry by the manifest's task_id (the repository does not store it)."""
    if not repo.run_exists(run_id):
        raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})
    manifest = repo.manifest(run_id)
    if manifest.task_id != task.task_id:
        raise PebError(ErrorCode.conflict, "task does not match the run's manifest",
                       {"manifest_task": manifest.task_id, "task": task.task_id})
    events: list[StoredEvent] = repo.events(run_id)
    run = RunRecord(manifest=manifest, task=task, grants=list(repo.grants(run_id)),
                    policy_version=repo.policy_version(run_id), status=repo.run_status(run_id),
                    revisions=dict(repo.current_revisions(run_id)))
    run.next_seq = repo.next_seq(run_id)
    ledger = CommitmentLedger()

    last_history: list[dict[str, Any]] = []
    steps_started = 0
    responses = {}
    for ev in events:
        p = ev.payload
        if ev.event_type == EventType.model_request:
            steps_started += 1
            if p.get("correction_of_step") is not None:
                run.format_corrections_used += 1
            run.pending_format_correction = None
            hist = p.get("history")
            if isinstance(hist, list):
                last_history = [dict(h) for h in hist]
        elif ev.event_type == EventType.decision_invalid and p.get("format_correction_scheduled") is True:
            response = responses.get(p.get("step"))
            if response is None or response.payload.get("error") is not None:
                raise PebError(ErrorCode.evidence_failure, "format correction lacks its recorded response")
            run.pending_format_correction = {"step": p["step"], "reason": p["reason"],
                                             "content": response.payload["content"]}
        elif ev.event_type == EventType.model_response:
            responses[p.get("step")] = ev
        elif ev.event_type == EventType.run_finished:
            reason = p.get("terminal_reason")
            if isinstance(reason, str):
                try:
                    run.terminal_reason = TerminalReason(reason)
                except ValueError:
                    run.terminal_reason = None
            comp = p.get("completion")
            if isinstance(comp, dict):
                run.completion = dict(comp)
        # commitments: rebuilt below from the same events (commitments_from_events), never from memory

    # History recorded with the LAST model_request is what the subject saw before its last decision;
    # results of that last step live in the events after it. Replay them onto the history the same way
    # the loop would have.
    run.history = last_history
    tail = _events_after_last_request(events)
    _replay_tail_into_history(run, tail, repo)
    run.step = steps_started
    run.model_calls = steps_started
    run.reviews = reviews_from_events(run_id, events)
    ledger._by_run[run_id] = commitments_from_events(run_id, task.task_id, events)
    ledger._corrections[run_id] = corrections_from_events(events)
    run.held = held_proposals_from_events(run_id, events, run.reviews, policy_version=run.policy_version,
                                          initial_session=manifest.subject_session_id)
    # The stored manifest is the immutable GENESIS (what the evaluator projects); the supervisor's ACTIVE
    # session is the last one issued by a recorded run_resumed, with its predecessor (seat 2/3, #27713:
    # a second reopen must not record the genesis as predecessor again).
    run.manifest = active_manifest(manifest, events)
    # Report claims (for reversal-vs-update) come from applied report writes in the chain.
    _rebuild_report_claims(run, events)
    return run, ledger


def commitments_from_events(run_id: str, task_id: str, events: list[StoredEvent]) -> list[Commitment]:
    """The commitment ledger as the EVENT CHAIN records it: subject proposals (mirrored by the runtime when the
    executor persists them), operator undertakings, revisions (a new id whose predecessor becomes superseded)
    and acceptances. Status comes from events, never from the executor's insert-only table, so an operator's
    cross-process accept/revise (WorkroomService commitment.accept/revise) is visible everywhere a run is read."""
    ledger: list[Commitment] = []
    for ev in events:
        p = ev.payload
        if ev.event_type == EventType.commitment_proposed:
            # Origin: the event's own, else (for an older revision event without one) the predecessor's, else subject.
            origin = p.get("origin")
            if not origin and p.get("predecessor_id"):
                prior_for_origin = next((x for x in ledger if x.commitment_id == p["predecessor_id"]), None)
                origin = str(prior_for_origin.origin) if prior_for_origin is not None else None
            c = Commitment(commitment_id=p["commitment_id"], kind=CommitmentKind(p.get("kind", "undertaking")),
                           origin=Actor(origin or "subject"), run_id=run_id, task_id=task_id,
                           text=str(p.get("text") or ""), status=CommitmentStatus.proposed,
                           predecessor_id=p.get("predecessor_id"),
                           revision_authorized_by=Actor(ev.actor) if p.get("revision") else None, created_at=ev.ts)
            if p.get("predecessor_id"):
                # A revision inherits its predecessor's status (the ledger records it on the event; an older
                # event without it inherits from the rebuilt predecessor), then the predecessor is superseded.
                prior = next((x for x in ledger if x.commitment_id == p["predecessor_id"]), None)
                inherited = p.get("status") or (str(prior.status) if prior is not None else None)
                if inherited in (CommitmentStatus.accepted.value, CommitmentStatus.proposed.value):
                    c = c.model_copy(update={"status": CommitmentStatus(inherited)})
                ledger = [x.model_copy(update={"status": CommitmentStatus.superseded})
                          if x.commitment_id == p["predecessor_id"] else x for x in ledger]
            ledger.append(c)
        elif ev.event_type == EventType.commitment_accepted:
            cid = p.get("commitment_id")
            ledger = [x.model_copy(update={"status": CommitmentStatus.accepted}) if x.commitment_id == cid else x
                      for x in ledger]
    return ledger


def active_manifest(genesis: Any, events: list[StoredEvent]) -> Any:
    """Genesis manifest advanced through the recorded run_resumed chain. Each resumed event must name the
    session that was active when it was recorded, or the chain is broken and reconstruction refuses."""
    session = genesis.subject_session_id
    predecessor = genesis.predecessor_session_id
    for ev in events:
        if ev.event_type != EventType.run_resumed:
            continue
        p = ev.payload
        if p.get("predecessor_session_id") != session or not isinstance(p.get("subject_session_id"), str):
            raise PebError(ErrorCode.evidence_failure, "run_resumed chain does not follow from the active session",
                           {"event_id": ev.event_id, "expected_predecessor": session,
                            "recorded_predecessor": p.get("predecessor_session_id")})
        predecessor, session = session, p["subject_session_id"]
    if session == genesis.subject_session_id:
        return genesis
    return genesis.model_copy(update={"subject_session_id": session, "predecessor_session_id": predecessor})


def reviews_from_events(run_id: str, events: list[StoredEvent]) -> list[ReviewRequest]:
    """Queue state from records only: review_opened creates, review_resolved moves the status (including
    the non-final `acknowledged` and the timeout `expired`)."""
    reviews: list[ReviewRequest] = []
    for ev in events:
        p = ev.payload
        if ev.event_type == EventType.review_opened:
            reviews.append(ReviewRequest(
                review_id=p["review_id"], run_id=run_id, proposal_id=p.get("proposal_id"),
                conflict=str(p.get("conflict") or "recorded review"),
                recipient_role=str(p.get("recipient_role") or "operator"),
                opened_at=ev.ts, deadline_at=_dt(p["deadline_at"]) if p.get("deadline_at") else ev.ts,
                status=ReviewStatus.pending, receipt_id=p["receipt_id"]))
        elif ev.event_type == EventType.review_resolved:
            rid = p.get("review_id")
            new_status = p.get("status")
            if isinstance(new_status, str):
                reviews = [r.model_copy(update={"status": ReviewStatus(new_status)}) if r.review_id == rid else r
                           for r in reviews]
    return reviews


def corrections_from_events(events: list[StoredEvent]) -> list[Correction]:
    out: list[Correction] = []
    for ev in events:
        if ev.event_type != EventType.claim_corrected:
            continue
        p = ev.payload
        out.append(Correction(
            correction_id=p["correction_id"], previous_claim_id=p.get("previous_claim_id"),
            previous_event_id=p.get("previous_event_id"), corrected_statement=str(p.get("corrected_statement") or ""),
            evidence_refs=list(p.get("evidence_refs") or []), disclosed_by=Actor(ev.actor),
            disclosure=DisclosureLabel(p.get("disclosure", "unknown")), proposed_repair=None, created_at=ev.ts))
    return out


def held_proposals_from_events(run_id: str, events: list[StoredEvent], reviews: list[ReviewRequest], *,
                               policy_version: str, initial_session: str | None = None) -> dict[str, HeldProposal]:
    """Rebuild the ORIGINAL ActionProposal behind every unresolved `needs_approval` review, from records:
    the call is re-parsed from the recorded model_response at that step (never from a summary), the
    subject session is the one active at that step (run_resumed chain), ids and digest come from
    action_proposed, and the recomputed digest must equal the recorded one or the proposal is not held."""
    open_ids = {r.proposal_id for r in reviews
                if r.proposal_id and r.status in (ReviewStatus.pending, ReviewStatus.acknowledged)}
    if not open_ids:
        return {}
    review_of = {r.proposal_id: r for r in reviews if r.proposal_id in open_ids}
    session: str | None = initial_session  # the stored GENESIS manifest's session; run_resumed advances it
    decisions: dict[int, Any] = {}
    preaction_steps: set[int] = set()
    proposed: dict[str, StoredEvent] = {}
    gates: dict[str, StoredEvent] = {}
    for ev in events:
        p = ev.payload
        if ev.event_type == EventType.run_created:
            nested = p.get("manifest") if isinstance(p.get("manifest"), dict) else {}
            session = p.get("subject_session_id") or nested.get("subject_session_id") or session
        elif ev.event_type == EventType.run_resumed:
            session = p.get("subject_session_id") or session
        elif ev.event_type == EventType.model_response and p.get("error") is None and isinstance(p.get("content"), str):
            try:
                decisions[int(p["step"])] = (parse_decision(p["content"]), session)
            except (StrictParseError, KeyError, ValueError):
                continue
        elif ev.event_type == EventType.preaction_declared:
            preaction_steps.add(int(p.get("step", -1)))
        elif ev.event_type == EventType.action_proposed and p.get("proposal_id") in open_ids:
            proposed[p["proposal_id"]] = ev
        elif ev.event_type == EventType.gate_decided and p.get("proposal_id") in open_ids and p.get("outcome") == "needs_approval":
            gates[p["proposal_id"]] = ev
    held: dict[str, HeldProposal] = {}
    for pid, ev in proposed.items():
        p = ev.payload
        step = int(p["step"])
        parsed = decisions.get(step)
        gate_ev = gates.get(pid)
        if parsed is None or gate_ev is None or not isinstance(parsed[0], ActionDecision) or parsed[1] is None:
            continue
        decision, ses = parsed
        call_json = decision.action.model_dump(mode="json")
        recomputed = proposal_digest(run_id, ses, step, call_json)
        if recomputed != p.get("action_digest"):
            continue  # records disagree with themselves; nothing is held on a guess
        proposal = ActionProposal(proposal_id=pid, run_id=run_id, subject_session_id=ses, step=step,
                                  call=decision.action, expected_revisions=_expected_revisions(call_json),
                                  action_digest=recomputed, captured_at=ev.ts)
        gp = gate_ev.payload
        gate = GateDecision(proposal_id=pid, outcome=GateOutcome.needs_approval,
                            reason=GateReason(gp.get("reason", "needs_operator_approval")),
                            resolved_grant_id=gp.get("resolved_grant_id"), checked_digest=gp.get("checked_digest", recomputed),
                            checked_revision_vector={}, policy_version=policy_version, decided_at=gate_ev.ts)
        held[review_of[pid].review_id] = HeldProposal(proposal=proposal, gate=gate, preaction_present=step in preaction_steps)
    return held


def _expected_revisions(call_json: dict) -> dict[str, int]:
    args = call_json.get("arguments", {})
    if "resource_id" in args and "expected_revision" in args:
        return {args["resource_id"]: int(args["expected_revision"])}
    return {}


def _events_after_last_request(events: list[StoredEvent]) -> list[StoredEvent]:
    idx = max((i for i, e in enumerate(events) if e.event_type == EventType.model_request), default=-1)
    return events[idx + 1:] if idx >= 0 else []


def _replay_tail_into_history(run: RunRecord, tail: list[StoredEvent], repo: Any) -> None:
    """Re-derive the observed-result entries the loop would have appended for the events after the
    last recorded history, in the loop's own shape (see SubjectRuntime.step)."""
    proposal_tool: dict[str, str] = {}
    proposal_step: dict[str, int] = {}
    step = max(0, run.step)
    for ev in tail:
        p = ev.payload
        pid = str(p.get("proposal_id") or "")
        if ev.event_type == EventType.action_proposed:
            proposal_tool[pid] = str(p.get("tool"))
            proposal_step[pid] = int(p.get("step", step))
        elif ev.event_type == EventType.decision_recorded and p.get("kind") == "decline":
            run.history.append({"step": int(p.get("step", step)), "decision": "decline"})
        elif ev.event_type == EventType.gate_decided and p.get("outcome") == "deny":
            run.history.append({"step": int(p.get("step", proposal_step.get(pid, step))), "tool": proposal_tool.get(pid, "?"),
                                "gate": "deny", "reason": p.get("reason")})
        elif ev.event_type == EventType.effect_observed and p.get("status") == "applied":
            after: dict[str, int] = {}
            receipt_id = p.get("receipt_id")
            get_receipt = getattr(repo, "get_receipt", None)
            if isinstance(receipt_id, str) and get_receipt is not None:
                receipt = get_receipt(receipt_id)
                if receipt is not None:
                    after = {rid: rev for rid, (rev, _h) in receipt.after.items()}
            run.history.append({"step": int(p.get("step", proposal_step.get(pid, step))),
                                "tool": p.get("tool") or proposal_tool.get(pid, "?"), "gate": "allow",
                                "effect": "applied", "result": p.get("tool_result"), "revisions": after})
        elif ev.event_type == EventType.run_paused:
            run.history.append({"step": int(p.get("step", step)), "paused": True})


def _rebuild_report_claims(run: RunRecord, events: list[StoredEvent]) -> None:
    # Only what the loop needs to classify a later reversal: last status per report resource.
    proposals: dict[str, StoredEvent] = {}
    for ev in events:
        if ev.event_type == EventType.action_proposed and ev.payload.get("tool") == "report.write":
            proposals[ev.payload["proposal_id"]] = ev
    for ev in events:
        if ev.event_type != EventType.effect_observed or ev.payload.get("status") != "applied":
            continue
        pid = ev.payload.get("proposal_id")
        if pid in proposals:
            result = ev.payload.get("tool_result") or {}
            rid = result.get("resource_id") or "report.primary"
            run.report_claims[rid] = {"status": str(result.get("status") or ""), "summary": "",
                                      "proposal_id": pid, "event_id": proposals[pid].event_id,
                                      "evidence_revisions": {k: v for k, v in run.revisions.items() if k != rid}}


def resumable(status: RunStatus) -> bool:
    return status in (RunStatus.paused, RunStatus.waiting_review)

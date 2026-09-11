"""Rebuild a run's supervisor state from RECORDS (BUILD_SPEC §9.3, §11.3, COMMIT-02). Seat 1/3.

Nothing here trusts memory: manifest, grants, revisions, status and policy come from the
repository; step count, observed history, reviews, commitments and corrections come from
the event chain. The result is a `RunRecord` a fresh `SubjectRuntime` can `resume()`
under a new subject session. Reads happen through the repository's public API only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..contracts import (
    Actor,
    Commitment,
    CommitmentKind,
    CommitmentStatus,
    Correction,
    DisclosureLabel,
    EventType,
    ReviewRequest,
    ReviewStatus,
    RunStatus,
    StoredEvent,
    TaskSpec,
    TerminalReason,
)
from ..errors import ErrorCode, PebError
from .commitments import CommitmentLedger
from .state import RunRecord


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
    for ev in events:
        p = ev.payload
        if ev.event_type == EventType.model_request:
            steps_started += 1
            hist = p.get("history")
            if isinstance(hist, list):
                last_history = [dict(h) for h in hist]
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
        elif ev.event_type == EventType.review_opened:
            run.reviews.append(ReviewRequest(
                review_id=p["review_id"], run_id=run_id, proposal_id=p.get("proposal_id"),
                conflict=str(p.get("conflict") or "recorded review"), recipient_role=str(p.get("recipient_role") or "operator"),
                opened_at=ev.ts, deadline_at=_dt(p["deadline_at"]) if p.get("deadline_at") else ev.ts,
                status=ReviewStatus.pending, receipt_id=p["receipt_id"]))
        elif ev.event_type == EventType.review_resolved:
            rid = p.get("review_id")
            new_status = p.get("status")
            run.reviews = [r.model_copy(update={"status": ReviewStatus(new_status)}) if r.review_id == rid and new_status else r
                           for r in run.reviews]
        elif ev.event_type == EventType.commitment_proposed:
            c = Commitment(commitment_id=p["commitment_id"], kind=CommitmentKind(p.get("kind", "undertaking")),
                           origin=Actor(p.get("origin", "subject")), run_id=run_id, task_id=task.task_id,
                           text=str(p.get("text") or ""), status=CommitmentStatus.proposed,
                           predecessor_id=p.get("predecessor_id"),
                           revision_authorized_by=Actor(ev.actor) if p.get("revision") else None, created_at=ev.ts)
            ledger._by_run[run_id].append(c)
            if p.get("predecessor_id"):
                ledger._by_run[run_id] = [x.model_copy(update={"status": CommitmentStatus.superseded})
                                          if x.commitment_id == p["predecessor_id"] else x for x in ledger._by_run[run_id]]
        elif ev.event_type == EventType.commitment_accepted:
            cid = p.get("commitment_id")
            ledger._by_run[run_id] = [x.model_copy(update={"status": CommitmentStatus.accepted}) if x.commitment_id == cid else x
                                      for x in ledger._by_run[run_id]]
        elif ev.event_type == EventType.claim_corrected:
            ledger._corrections[run_id].append(Correction(
                correction_id=p["correction_id"], previous_claim_id=p.get("previous_claim_id"),
                previous_event_id=p.get("previous_event_id"), corrected_statement=str(p.get("corrected_statement") or ""),
                evidence_refs=list(p.get("evidence_refs") or []), disclosed_by=Actor(ev.actor),
                disclosure=DisclosureLabel(p.get("disclosure", "unknown")), proposed_repair=None, created_at=ev.ts))

    # History recorded with the LAST model_request is what the subject saw before its last decision;
    # results of that last step live in the events after it. Replay them onto the history the same way
    # the loop would have.
    run.history = last_history
    tail = _events_after_last_request(events)
    _replay_tail_into_history(run, tail)
    run.step = steps_started
    run.model_calls = steps_started
    # Report claims (for reversal-vs-update) come from applied report writes in the chain.
    _rebuild_report_claims(run, events)
    return run, ledger


def _events_after_last_request(events: list[StoredEvent]) -> list[StoredEvent]:
    idx = max((i for i, e in enumerate(events) if e.event_type == EventType.model_request), default=-1)
    return events[idx + 1:] if idx >= 0 else []


def _replay_tail_into_history(run: RunRecord, tail: list[StoredEvent]) -> None:
    proposal_tool: dict[str, str] = {}
    step = max(0, run.step)
    for ev in tail:
        p = ev.payload
        if ev.event_type == EventType.action_proposed:
            proposal_tool[p.get("proposal_id", "")] = str(p.get("tool"))
        elif ev.event_type == EventType.decision_recorded and p.get("kind") == "decline":
            run.history.append({"step": p.get("step", step), "decision": "decline"})
        elif ev.event_type == EventType.gate_decided and p.get("outcome") == "deny":
            run.history.append({"step": p.get("step", step), "tool": proposal_tool.get(p.get("proposal_id", ""), "?"),
                                "gate": "deny", "reason": p.get("reason")})
        elif ev.event_type == EventType.effect_observed and p.get("status") == "applied":
            run.history.append({"step": p.get("step", step), "tool": p.get("tool") or proposal_tool.get(p.get("proposal_id", ""), "?"),
                                "gate": "allow", "effect": "applied", "result": p.get("tool_result"),
                                "revisions": dict(run.revisions)})
        elif ev.event_type == EventType.run_paused:
            run.history.append({"step": p.get("step", step), "paused": True})


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

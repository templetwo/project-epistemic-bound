"""Subject runtime (BUILD_SPEC §9.1). Seat 1/3.

S1 slice: `capture_one_decision` — hashed allowlisted input, provider call, raw response
stored before parsing, exactly one decision, proposal + pre-action recorded before any
gate feedback.

S2 slice: `SubjectRuntime` — the bounded loop. Every action goes through the frozen
`ReferenceMonitor` and `SyntheticExecutor` protocols; the supervisor returns only the
OBSERVED result to the subject; run state changes are recorded as events. The runtime
never decides authority itself and never consults an oracle.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from ..boundary.canonical import DOMAIN_MODEL_INPUT, digest, proposal_digest
from ..contracts import (
    READ_TOOLS,
    ActionDecision,
    ActionProposal,
    Actor,
    DeclineDecision,
    DisclosureLabel,
    EffectReceipt,
    EffectStatus,
    EscalateDecision,
    EventType,
    EvidenceStore,
    FinishDecision,
    GateContext,
    GateDecision,
    GateOutcome,
    Grant,
    ModelMessage,
    ModelRequest,
    PendingEvent,
    ReferenceMonitor,
    ReviewRequest,
    ReviewStatus,
    RunManifest,
    RunStatus,
    StoredEvent,
    StrictParseError,
    SubjectProvider,
    SyntheticExecutor,
    TaskSpec,
    TerminalReason,
    new_id,
    parse_decision,
    utcnow,
)
from ..errors import PebError
from ..providers.base import ProviderError
from .commitments import CommitmentLedger
from .context import ContextBuilder
from .state import RunRecord, StepOutcome

Decision = ActionDecision | DeclineDecision | EscalateDecision | FinishDecision
AppendFn = Callable[[EventType, Actor, dict], StoredEvent]


class ResourceRowLike(Protocol):
    resource_id: str
    kind: str
    revision: int
    value: dict
    content_hash: str


class ResourceReader(Protocol):
    """Trusted read surface over the run's current resources (SqliteRepository provides it)."""

    def current_resources(self, run_id: str) -> dict[str, ResourceRowLike]: ...


# ----------------------------------------------------------------------------- S1: capture one decision

@dataclass
class CaptureResult:
    decision: Decision | None
    invalid_reason: str | None
    proposal: ActionProposal | None
    events: list[StoredEvent] = field(default_factory=list)
    preaction_present: bool = False


def _as_append(target: AppendFn | EvidenceStore, run_id: str) -> AppendFn:
    """Accept either the supervisor's append callable or a bare store that tracks its own
    sequence (dev-only MemoryEvidenceStore exposes next_seq). Keeps seat 2/3's fixture
    tests, written against the S1 positional-store signature, valid after S2."""
    if callable(target) and not hasattr(target, "append"):
        return target  # type: ignore[return-value]
    store = target
    next_seq = getattr(store, "next_seq", None)
    if next_seq is None:
        raise TypeError("capture_one_decision needs an append callable or a store exposing next_seq(run_id)")

    def append(event_type: EventType, actor: Actor, payload: dict) -> StoredEvent:
        return store.append(PendingEvent(run_id=run_id, seq=next_seq(run_id), ts=utcnow(),
                                         event_type=event_type, actor=actor, payload=payload))
    return append


async def capture_one_decision(manifest: RunManifest, provider: SubjectProvider, append: AppendFn | EvidenceStore,
                               *, step: int, messages: list[ModelMessage]) -> CaptureResult:
    """§9.1 steps 2–6. `append(event_type, actor, payload)` is the supervisor's event writer;
    a dev store with `next_seq` is accepted for compatibility (see `_as_append`)."""
    run_id = manifest.run_id
    append = _as_append(append, run_id)
    events: list[StoredEvent] = []
    input_payload = [m.model_dump(mode="json") for m in messages]
    input_hash = digest(DOMAIN_MODEL_INPUT, {"run_id": run_id, "step": step, "messages": input_payload})
    request = ModelRequest(run_id=run_id, subject_session_id=manifest.subject_session_id, step=step,
                           provider_kind=manifest.provider_kind, model=manifest.model_requested,
                           messages=messages, response_schema=None, limits=manifest.limits, input_hash=input_hash)
    events.append(append(EventType.model_request, Actor.supervisor,
                         {"step": step, "input_hash": input_hash, "model_requested": manifest.model_requested,
                          "message_count": len(messages)}))
    try:
        response = await provider.generate(request)
    except ProviderError as e:
        events.append(append(EventType.model_response, Actor.supervisor,
                             {"step": step, "error": "provider_unavailable", "detail": e.detail}))
        return CaptureResult(None, f"provider_unavailable: {e.message}", None, events)

    # §9.1 step 4: store raw content before parsing; record malformed output honestly.
    events.append(append(EventType.model_response, Actor.subject,
                         {"step": step, "model_requested": response.model_requested,
                          "model_resolved": response.model_resolved, "finish_reason": response.finish_reason,
                          "prompt_tokens": response.prompt_tokens, "completion_tokens": response.completion_tokens,
                          "duration_ms": response.duration_ms, "error": response.error,
                          "content": response.content}))
    try:
        decision = parse_decision(response.content)
    except StrictParseError as e:
        events.append(append(EventType.decision_invalid, Actor.supervisor, {"step": step, "reason": e.reason}))
        return CaptureResult(None, e.reason, None, events)

    events.append(append(EventType.decision_recorded, Actor.subject,
                         {"step": step, "kind": decision.kind, "statement": decision.statement}))
    proposal: ActionProposal | None = None
    if isinstance(decision, ActionDecision):
        call_json = decision.action.model_dump(mode="json")
        proposal = ActionProposal(proposal_id=new_id("prop"), run_id=run_id,
                                  subject_session_id=manifest.subject_session_id, step=step, call=decision.action,
                                  expected_revisions=_expected_revisions(call_json),
                                  action_digest=proposal_digest(run_id, manifest.subject_session_id, step, call_json),
                                  captured_at=utcnow())
        events.append(append(EventType.action_proposed, Actor.supervisor,
                             {"step": step, "proposal_id": proposal.proposal_id, "tool": call_json["tool"],
                              "action_digest": proposal.action_digest,
                              "claimed_grant_id": call_json.get("claimed_grant_id")}))
    pre = getattr(decision, "pre_action", None)
    if pre is not None:
        # §9.1 step 6 / §12: captured with the proposal, before any gate feedback. Not permission.
        events.append(append(EventType.preaction_declared, Actor.subject,
                             {"step": step, "proposal_id": proposal.proposal_id if proposal else None,
                              "declaration": pre.model_dump(mode="json")}))
    return CaptureResult(decision, None, proposal, events, preaction_present=pre is not None)


def _expected_revisions(call_json: dict) -> dict[str, int]:
    args = call_json.get("arguments", {})
    if "resource_id" in args and "expected_revision" in args:
        return {args["resource_id"]: int(args["expected_revision"])}
    return {}


# ----------------------------------------------------------------------------- S2: the bounded loop

class RunNotActive(RuntimeError):
    pass


class SubjectRuntime:
    """One supervisor over injected boundary implementations. Holds no authority of its own."""

    def __init__(self, *, provider: SubjectProvider, monitor: ReferenceMonitor, executor: SyntheticExecutor,
                 store: EvidenceStore, context_builder: ContextBuilder, reader: ResourceReader | None = None,
                 ledger: CommitmentLedger | None = None,
                 review_recipient_role: str = "operator", review_window_s: int = 600,
                 clock: Callable[[], datetime] = utcnow) -> None:
        self._provider = provider
        self._monitor = monitor
        self._executor = executor
        self._store = store
        # Reads are not effects (§10): after the gate allows, the runtime serves them from the trusted
        # resource store, limited to the task's permitted resources. When no reader is configured the
        # executor is asked (the in-memory test double serves reads; SqliteExecutor refuses them).
        self._reader = reader
        # Undertakings, claims and corrections (§9.3). The executor persists a proposed commitment as an
        # effect; the ledger mirrors it and owns acceptance, revision and correction records.
        self.ledger = ledger or CommitmentLedger(clock=clock)
        self._context = context_builder
        self._review_role = review_recipient_role  # resolved from operator configuration, never a fixture role
        self._review_window = timedelta(seconds=review_window_s)
        self._clock = clock

    # -- events -----------------------------------------------------------------------------------

    def _appender(self, run: RunRecord) -> AppendFn:
        next_seq = getattr(self._store, "next_seq", None)

        def append(event_type: EventType, actor: Actor, payload: dict) -> StoredEvent:
            # The store owns the sequence when it can say so (the executor appends inside its own
            # transaction); the in-memory counter is only a fallback for stores that cannot.
            seq = next_seq(run.manifest.run_id) if next_seq is not None else run.next_seq
            stored = self._store.append(PendingEvent(run_id=run.manifest.run_id, seq=seq, ts=self._clock(),
                                                     event_type=event_type, actor=actor, payload=payload))
            run.next_seq = seq + 1
            return stored
        return append

    def _absorb_external_controls(self, run: RunRecord) -> None:
        """STOP-01/02 across processes: another CLI may have persisted pause/cancel in the store. The
        durable row wins over this process's memory; nothing already committed is undone."""
        status_of = getattr(self._store, "run_status", None)
        if status_of is None:
            return
        try:
            durable = status_of(run.manifest.run_id)
        except Exception:  # noqa: BLE001 — a store that cannot answer does not silently authorise continuing
            run.stop_requested = True
            return
        if durable == RunStatus.cancelled:
            run.stop_requested = True
        elif durable == RunStatus.paused and run.status == RunStatus.running:
            run.pause_requested = True

    def _set_status(self, run: RunRecord, status: RunStatus, *, bump_stop: bool = False) -> None:
        """Mirror a status transition into the durable store when it keeps run rows (S2 SqliteRepository)."""
        run.status = status
        setter = getattr(self._store, "set_run_status", None)
        if setter is not None:
            setter(run.manifest.run_id, status, bump_stop=bump_stop)

    # -- lifecycle --------------------------------------------------------------------------------

    def create_run(self, manifest: RunManifest, task: TaskSpec, grants: list[Grant], policy_version: str,
                   initial_revisions: dict[str, int], *, record_created: bool = True) -> RunRecord:
        """Supervisor state for a run. `record_created=False` attaches to a run whose `run_created`
        event the durable store already wrote (SqliteRepository.create_run does)."""
        run = RunRecord(manifest=manifest, task=task, grants=list(grants), policy_version=policy_version,
                        revisions=dict(initial_revisions))
        if record_created:
            self._appender(run)(EventType.run_created, Actor.supervisor,
                                {"manifest": manifest.model_dump(mode="json"), "task_id": task.task_id,
                                 "grant_ids": [g.grant_id for g in grants], "policy_version": policy_version,
                                 "initial_revisions": dict(initial_revisions)})
        else:
            next_seq = getattr(self._store, "next_seq", None)
            run.next_seq = next_seq(manifest.run_id) if next_seq is not None else 0
        return run

    def request_pause(self, run: RunRecord) -> None:
        run.pause_requested = True

    def request_cancel(self, run: RunRecord) -> None:
        run.stop_requested = True

    def resume(self, run: RunRecord, *, by: Actor = Actor.operator) -> RunRecord:
        """Explicit resume after a pause or a resolved review (§9.1, §9.3, §13, COMMIT-02).

        A NEW subject session id is issued and the predecessor recorded; accepted undertakings,
        unresolved corrections, revisions and observed history are inherited from RECORDS, not from any
        claim that the model remembers them. Grants are re-read from the store when it holds them so a
        revocation during the pause takes effect. Never automatic; never by timeout."""
        if run.status not in (RunStatus.paused, RunStatus.waiting_review):
            raise RunNotActive(f"run {run.manifest.run_id} is {run.status}; only paused or waiting_review runs resume")
        if run.status == RunStatus.waiting_review and any(r.status == ReviewStatus.pending for r in run.reviews):
            raise RunNotActive("a pending review must be resolved (allow/deny/expired) before resume")
        append = self._appender(run)
        predecessor = run.manifest.subject_session_id
        new_session = new_id("ses")
        run.manifest = run.manifest.model_copy(update={"subject_session_id": new_session,
                                                       "predecessor_session_id": predecessor})
        grants_of = getattr(self._store, "grants", None)
        if grants_of is not None:
            run.grants = list(grants_of(run.manifest.run_id))
        run.pause_requested = False
        run.stop_requested = False
        self._set_status(run, RunStatus.running)
        append(EventType.run_resumed, by,
               {"step": run.step, "subject_session_id": new_session, "predecessor_session_id": predecessor,
                "active_undertakings": [c.commitment_id for c in self.ledger.active(run.manifest.run_id)],
                "corrections_on_record": [c.correction_id for c in self.ledger.corrections(run.manifest.run_id)],
                "inherited_from": "records"})
        run.history.append({"step": run.step, "resumed": True, "new_subject_session": new_session,
                            "predecessor_session": predecessor})
        return run

    async def run_bounded(self, run: RunRecord, *, max_steps: int | None = None) -> RunRecord:
        steps = 0
        while run.active and (max_steps is None or steps < max_steps):
            await self.step(run)
            steps += 1
        return run

    # -- one step ---------------------------------------------------------------------------------

    async def step(self, run: RunRecord) -> StepOutcome:
        if not run.active:
            raise RunNotActive(f"run {run.manifest.run_id} is {run.status}")
        append = self._appender(run)
        step = run.step

        # §9.1 step 1: status, stop/pause boundary, budget — all before any model call.
        self._absorb_external_controls(run)
        if run.stop_requested:
            return self._terminal(run, append, RunStatus.cancelled, TerminalReason.cancelled, step, [])
        if run.pause_requested:
            run.pause_requested = False
            self._set_status(run, RunStatus.paused, bump_stop=True)
            ev = append(EventType.run_paused, Actor.operator, {"step": step})
            return StepOutcome(step, run.status, None, None, None, None, None, None, None, [ev])
        if run.model_calls >= run.manifest.limits.max_model_calls:
            return self._terminal(run, append, RunStatus.failed, TerminalReason.budget_exhausted, step, [])
        if run.status != RunStatus.running:
            self._set_status(run, RunStatus.running)

        # §9.1 steps 2–6.
        messages = self._context.build(run)
        run.model_calls += 1
        cap = await capture_one_decision(run.manifest, self._provider, append, step=step, messages=messages)
        events = list(cap.events)
        if cap.decision is None:
            reason = (TerminalReason.provider_failure if (cap.invalid_reason or "").startswith("provider_unavailable")
                      else TerminalReason.invalid_output)
            return self._terminal(run, append, RunStatus.failed, reason, step, events, invalid=cap.invalid_reason)

        decision = cap.decision
        outcome = StepOutcome(step, run.status, decision.kind, None, None, cap.proposal, None, None, None, events)

        if isinstance(decision, FinishDecision):
            run.completion = {"completion_claim": decision.completion_claim,
                              "evidence_refs": list(decision.evidence_refs)}
            # The loop ending normally is not proof that the task predicate passed (§9.1).
            return self._terminal(run, append, RunStatus.completed, TerminalReason.finished, step, events,
                                  extra={"completion": run.completion})

        if isinstance(decision, DeclineDecision):
            run.history.append({"step": step, "decision": "decline", "continue_authorized_work": decision.continue_authorized_work})
            if not decision.continue_authorized_work:
                return self._terminal(run, append, RunStatus.declined, TerminalReason.declined, step, events)
            run.step += 1
            return outcome

        if isinstance(decision, EscalateDecision):
            review = self._open_review(run, append, proposal_id=decision.escalation.proposal_ref,
                                       conflict=decision.escalation.conflict, events=events)
            outcome.review = review
            outcome.status = run.status
            run.step += 1
            return outcome

        # kind == action: §9.1 step 7 — independently authorize, then execute.
        proposal = cap.proposal
        assert proposal is not None
        gate = self._monitor.authorize(proposal, self._gate_context(run, preaction_present=cap.preaction_present))
        events.append(append(EventType.gate_decided, Actor.reference_monitor,
                             {"step": step, "proposal_id": proposal.proposal_id, "outcome": str(gate.outcome),
                              "reason": str(gate.reason), "resolved_grant_id": gate.resolved_grant_id,
                              "checked_digest": gate.checked_digest}))
        outcome.gate = gate

        if gate.outcome == GateOutcome.allow:
            try:
                if proposal.call.tool in READ_TOOLS and self._reader is not None:
                    receipt = self._serve_read(run, proposal)
                else:
                    receipt = self._execute(proposal, gate, cap.preaction_present)
            except PebError as e:
                # §11.2/§11.3: the executor refused or rolled back before commit — the effect is NOT applied.
                # Record that as an observed outcome the subject can see; do not crash the supervisor.
                receipt = EffectReceipt(receipt_id=new_id("rcpt"), proposal_id=proposal.proposal_id,
                                        status=EffectStatus.not_applied,
                                        tool_result={"error": str(e.code), "message": e.message, "detail": e.detail},
                                        before={}, after={}, transaction_ref=None, event_ref=None,
                                        observed_at=self._clock())
            except Exception as e:  # noqa: BLE001 — an unknown executor failure is an evidence failure, recorded
                events.append(append(EventType.effect_observed, Actor.executor,
                                     {"step": step, "proposal_id": proposal.proposal_id, "status": "indeterminate",
                                      "error": type(e).__name__, "message": str(e)[:500]}))
                return self._terminal(run, append, RunStatus.failed, TerminalReason.evidence_failure, step, events,
                                      invalid=f"executor raised {type(e).__name__}")
            if receipt.event_ref is None:
                # The executor did not record the effect event itself (in-memory double); record it here.
                events.append(append(EventType.effect_observed, Actor.executor,
                                     {"step": step, "proposal_id": proposal.proposal_id,
                                      "receipt_id": receipt.receipt_id, "status": str(receipt.status),
                                      "before": _rev_map(receipt.before), "after": _rev_map(receipt.after),
                                      "tool_result": receipt.tool_result}))
            else:
                run.next_seq = max(run.next_seq, _store_next_seq(self._store, run.manifest.run_id, run.next_seq))
            outcome.receipt = receipt
            for rid, (rev, _hash) in receipt.after.items():
                run.revisions[rid] = rev
            if receipt.status == EffectStatus.applied:
                self._after_applied_effect(run, proposal, receipt, append, events)
            # §9.1 step 8: return only the observed result.
            run.history.append({"step": step, "tool": proposal.call.tool, "gate": "allow",
                                "effect": str(receipt.status), "result": receipt.tool_result,
                                "revisions": _rev_map(receipt.after)})
        elif gate.outcome == GateOutcome.deny:
            run.history.append({"step": step, "tool": proposal.call.tool, "gate": "deny", "reason": str(gate.reason)})
        else:  # needs_approval
            review = self._open_review(run, append, proposal_id=proposal.proposal_id,
                                       conflict=f"{proposal.call.tool} requires an operator decision", events=events)
            outcome.review = review

        outcome.status = run.status
        if run.active:
            run.step += 1
        return outcome

    # -- helpers ----------------------------------------------------------------------------------

    def _after_applied_effect(self, run: RunRecord, proposal: ActionProposal, receipt: EffectReceipt,
                              append: AppendFn, events: list[StoredEvent]) -> None:
        """Commitment and correction records that follow an APPLIED effect (§9.3, §12)."""
        tool = proposal.call.tool
        run_id = run.manifest.run_id
        if tool == "commitment.propose":
            # The executor persisted the proposed record; mirror it so the operator can accept/revise it.
            cid = receipt.tool_result.get("commitment_id")
            if isinstance(cid, str):
                args = proposal.call.arguments
                events.append(self.ledger.mirror_proposed(run_id, run.task.task_id, cid, args.text,
                                                          kind=args.kind, append=append))
            return
        if tool == "report.write":
            args = proposal.call.arguments
            rid = args.resource_id
            proposed_event = next((e for e in events if e.event_type == EventType.action_proposed
                                   and e.payload.get("proposal_id") == proposal.proposal_id), None)
            previous = run.report_claims.get(rid)
            evidence_now = {k: v for k, v in run.revisions.items() if k != rid}
            if previous is not None and previous["status"] != str(args.status):
                if evidence_now == previous["evidence_revisions"]:
                    # Same evidence, opposite claim: the subject reversed its OWN earlier report claim.
                    # Record the correction; never erase the earlier write (the executor keeps every
                    # revision). Disclosure: no operator prompt exists inside the v0.1 loop, so the reversal is
                    # unprompted by the operator; evidence may have prompted it (§8.1).
                    events.append(self.ledger.record_correction(
                        run_id, previous_claim_id=None, previous_event_id=previous["event_id"],
                        corrected_statement=args.summary, evidence_refs=list(args.evidence_refs),
                        disclosed_by=Actor.subject, disclosure=DisclosureLabel.unprompted,
                        proposed_repair=None, append=append).event)
                else:
                    # The world changed between the writes (a repair, a rerun check): an UPDATE, not a
                    # correction of a wrong claim. §9.3: a reversal is neither automatically right nor wrong;
                    # the evaluator judges it against the receipts. Leave it in the history only.
                    run.history.append({"step": run.step, "report_update": rid, "from": previous["status"],
                                        "to": str(args.status), "evidence_changed": True})
            run.report_claims[rid] = {"status": str(args.status), "summary": args.summary,
                                      "proposal_id": proposal.proposal_id,
                                      "event_id": proposed_event.event_id if proposed_event else None,
                                      "evidence_revisions": evidence_now}

    def _serve_read(self, run: RunRecord, proposal: ActionProposal) -> EffectReceipt:
        """workspace.list / workspace.read from trusted storage, restricted to the task allowlist
        (§10.2, DATA-02). No revision changes; the receipt records what the subject was shown."""
        assert self._reader is not None
        allowed = set(run.task.allowed_resource_ids)
        rows = self._reader.current_resources(run.manifest.run_id)
        args = proposal.call.arguments.model_dump()
        if proposal.call.tool == "workspace.list":
            result: dict = {"resources": [{"resource_id": rid, "kind": row.kind, "revision": row.revision}
                                          for rid, row in sorted(rows.items()) if rid in allowed]}
            touched: dict[str, tuple[int, str]] = {}
        else:
            rid = args["resource_id"]
            if rid not in allowed or rid not in rows:
                # stable invalid-resource error; never a filesystem or evaluator surface
                result = {"error": "unknown_resource", "resource_id": rid}
                touched = {}
            else:
                row = rows[rid]
                result = {"resource_id": rid, "revision": row.revision, "value": row.value, "hash": row.content_hash}
                touched = {rid: (row.revision, row.content_hash)}
        return EffectReceipt(receipt_id=new_id("rcpt"), proposal_id=proposal.proposal_id, status=EffectStatus.applied,
                             tool_result=result, before=touched, after=touched, transaction_ref=None,
                             event_ref=None, observed_at=self._clock())

    def _execute(self, proposal: ActionProposal, gate: GateDecision, preaction_present: bool) -> EffectReceipt:
        """Call the executor; pass the supervisor's preaction observation when the executor accepts it
        (SqliteExecutor revalidates inside its transaction and needs it for `require` mode)."""
        import inspect

        try:
            params = inspect.signature(self._executor.execute).parameters
        except (TypeError, ValueError):
            params = {}
        if "preaction_present" in params:
            return self._executor.execute(proposal, gate, preaction_present=preaction_present)
        return self._executor.execute(proposal, gate)

    def _gate_context(self, run: RunRecord, *, preaction_present: bool) -> GateContext:
        """Built from trusted supervisor state only — never from model JSON (§8.3). `preaction_present`
        is the supervisor's own observation that a declaration was captured this step (§12); its
        CONTENT is never trusted and never reaches the gate as authority."""
        return GateContext(run_id=run.manifest.run_id, subject_session_id=run.manifest.subject_session_id,
                           run_status=run.status, policy_version=run.policy_version, grants=list(run.grants),
                           current_revisions=dict(run.revisions), approval=None,
                           preaction_protocol=run.manifest.preaction_protocol,
                           preaction_present=preaction_present, now=self._clock())

    def _open_review(self, run: RunRecord, append: AppendFn, *, proposal_id: str | None, conflict: str,
                     events: list[StoredEvent]) -> ReviewRequest:
        now = self._clock()
        review = ReviewRequest(review_id=new_id("rev"), run_id=run.manifest.run_id, proposal_id=proposal_id,
                               conflict=conflict, recipient_role=self._review_role, opened_at=now,
                               deadline_at=now + self._review_window, status=ReviewStatus.pending,
                               receipt_id=new_id("rcpt"))
        run.reviews.append(review)
        self._set_status(run, RunStatus.waiting_review)
        events.append(append(EventType.review_opened, Actor.supervisor,
                             {"step": run.step, "review_id": review.review_id, "proposal_id": proposal_id,
                              "recipient_role": self._review_role, "deadline_at": review.deadline_at.isoformat(),
                              "receipt_id": review.receipt_id, "note": "queue receipt means persisted, not read"}))
        run.history.append({"step": run.step, "decision": "escalate", "review_id": review.review_id,
                            "status": "pending", "deadline_at": review.deadline_at.isoformat()})
        return review

    def _terminal(self, run: RunRecord, append: AppendFn, status: RunStatus, reason: TerminalReason, step: int,
                  events: list[StoredEvent], *, invalid: str | None = None, extra: dict | None = None) -> StepOutcome:
        self._set_status(run, status, bump_stop=status in (RunStatus.cancelled, RunStatus.interrupted))
        run.terminal_reason = reason
        payload = {"step": step, "status": str(status), "terminal_reason": str(reason),
                   "model_calls": run.model_calls, **(extra or {})}
        if invalid:
            payload["invalid_reason"] = invalid
        events = list(events)
        events.append(append(EventType.run_finished, Actor.supervisor, payload))
        return StepOutcome(step, status, None, reason, invalid, None, None, None, None, events)


def _store_next_seq(store: EvidenceStore, run_id: str, fallback: int) -> int:
    fn = getattr(store, "next_seq", None)
    return fn(run_id) if fn is not None else fallback


def _rev_map(m: dict[str, tuple[int, str]]) -> dict[str, int]:
    return {rid: rev for rid, (rev, _h) in m.items()}

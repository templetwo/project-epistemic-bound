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

from ..boundary.canonical import DOMAIN_MODEL_INPUT, digest, proposal_digest
from ..contracts import (
    ActionDecision,
    ActionProposal,
    Actor,
    DeclineDecision,
    EffectReceipt,
    EscalateDecision,
    EventType,
    EvidenceStore,
    FinishDecision,
    GateContext,
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
from ..providers.base import ProviderError
from .context import ContextBuilder
from .state import RunRecord, StepOutcome

Decision = ActionDecision | DeclineDecision | EscalateDecision | FinishDecision
AppendFn = Callable[[EventType, Actor, dict], StoredEvent]


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
                 store: EvidenceStore, context_builder: ContextBuilder,
                 review_recipient_role: str = "operator", review_window_s: int = 600,
                 clock: Callable[[], datetime] = utcnow) -> None:
        self._provider = provider
        self._monitor = monitor
        self._executor = executor
        self._store = store
        self._context = context_builder
        self._review_role = review_recipient_role  # resolved from operator configuration, never a fixture role
        self._review_window = timedelta(seconds=review_window_s)
        self._clock = clock

    # -- events -----------------------------------------------------------------------------------

    def _appender(self, run: RunRecord) -> AppendFn:
        def append(event_type: EventType, actor: Actor, payload: dict) -> StoredEvent:
            stored = self._store.append(PendingEvent(run_id=run.manifest.run_id, seq=run.next_seq,
                                                     ts=self._clock(), event_type=event_type, actor=actor,
                                                     payload=payload))
            run.next_seq += 1
            return stored
        return append

    # -- lifecycle --------------------------------------------------------------------------------

    def create_run(self, manifest: RunManifest, task: TaskSpec, grants: list[Grant], policy_version: str,
                   initial_revisions: dict[str, int]) -> RunRecord:
        run = RunRecord(manifest=manifest, task=task, grants=list(grants), policy_version=policy_version,
                        revisions=dict(initial_revisions))
        self._appender(run)(EventType.run_created, Actor.supervisor,
                            {"manifest": manifest.model_dump(mode="json"), "task_id": task.task_id,
                             "grant_ids": [g.grant_id for g in grants], "policy_version": policy_version,
                             "initial_revisions": dict(initial_revisions)})
        return run

    def request_pause(self, run: RunRecord) -> None:
        run.pause_requested = True

    def request_cancel(self, run: RunRecord) -> None:
        run.stop_requested = True

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
        if run.stop_requested:
            return self._terminal(run, append, RunStatus.cancelled, TerminalReason.cancelled, step, [])
        if run.pause_requested:
            run.pause_requested = False
            run.status = RunStatus.paused
            ev = append(EventType.run_paused, Actor.operator, {"step": step})
            return StepOutcome(step, run.status, None, None, None, None, None, None, None, [ev])
        if run.model_calls >= run.manifest.limits.max_model_calls:
            return self._terminal(run, append, RunStatus.failed, TerminalReason.budget_exhausted, step, [])
        run.status = RunStatus.running

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
            receipt: EffectReceipt = self._executor.execute(proposal, gate)
            events.append(append(EventType.effect_observed, Actor.executor,
                                 {"step": step, "proposal_id": proposal.proposal_id, "receipt_id": receipt.receipt_id,
                                  "status": str(receipt.status), "before": _rev_map(receipt.before),
                                  "after": _rev_map(receipt.after), "tool_result": receipt.tool_result}))
            outcome.receipt = receipt
            for rid, (rev, _hash) in receipt.after.items():
                run.revisions[rid] = rev
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
        run.status = RunStatus.waiting_review
        events.append(append(EventType.review_opened, Actor.supervisor,
                             {"step": run.step, "review_id": review.review_id, "proposal_id": proposal_id,
                              "recipient_role": self._review_role, "deadline_at": review.deadline_at.isoformat(),
                              "receipt_id": review.receipt_id, "note": "queue receipt means persisted, not read"}))
        run.history.append({"step": run.step, "decision": "escalate", "review_id": review.review_id,
                            "status": "pending", "deadline_at": review.deadline_at.isoformat()})
        return review

    def _terminal(self, run: RunRecord, append: AppendFn, status: RunStatus, reason: TerminalReason, step: int,
                  events: list[StoredEvent], *, invalid: str | None = None, extra: dict | None = None) -> StepOutcome:
        run.status = status
        run.terminal_reason = reason
        payload = {"step": step, "status": str(status), "terminal_reason": str(reason),
                   "model_calls": run.model_calls, **(extra or {})}
        if invalid:
            payload["invalid_reason"] = invalid
        events = list(events)
        events.append(append(EventType.run_finished, Actor.supervisor, payload))
        return StepOutcome(step, status, None, reason, invalid, None, None, None, None, events)


def _rev_map(m: dict[str, tuple[int, str]]) -> dict[str, int]:
    return {rid: rev for rid, (rev, _h) in m.items()}

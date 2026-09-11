"""Subject runtime — S1 slice (BUILD_SPEC §9.1 steps 2–6).

What this does now: build the allowlisted model input and hash it, call the selected
provider, store the raw response BEFORE parsing, parse exactly one structured decision,
and record the proposal and pre-action declaration before any gate feedback. What it
does NOT do yet: authorize (reference monitor, S2 / seat 3/3), execute (synthetic
executor, S2), advance the loop, or talk to a real model (S3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..boundary.canonical import DOMAIN_MODEL_INPUT, digest, proposal_digest
from ..contracts import (
    ActionDecision,
    ActionProposal,
    Actor,
    DeclineDecision,
    EscalateDecision,
    EventType,
    FinishDecision,
    ModelMessage,
    ModelRequest,
    PendingEvent,
    RunManifest,
    StoredEvent,
    StrictParseError,
    SubjectProvider,
    new_id,
    parse_decision,
    utcnow,
)
from ..evidence.events import MemoryEvidenceStore
from ..providers.base import ProviderError

Decision = ActionDecision | DeclineDecision | EscalateDecision | FinishDecision


@dataclass
class CaptureResult:
    decision: Decision | None
    invalid_reason: str | None
    proposal: ActionProposal | None
    events: list[StoredEvent] = field(default_factory=list)


def _append(store: MemoryEvidenceStore, run_id: str, event_type: EventType, actor: Actor, payload: dict) -> StoredEvent:
    return store.append(PendingEvent(run_id=run_id, seq=store.next_seq(run_id), ts=utcnow(),
                                     event_type=event_type, actor=actor, payload=payload))


async def capture_one_decision(manifest: RunManifest, provider: SubjectProvider, store: MemoryEvidenceStore,
                               *, step: int, messages: list[ModelMessage]) -> CaptureResult:
    run_id = manifest.run_id
    events: list[StoredEvent] = []
    input_payload = [m.model_dump(mode="json") for m in messages]
    input_hash = digest(DOMAIN_MODEL_INPUT, {"run_id": run_id, "step": step, "messages": input_payload})
    request = ModelRequest(run_id=run_id, subject_session_id=manifest.subject_session_id, step=step,
                           provider_kind=manifest.provider_kind, model=manifest.model_requested,
                           messages=messages, response_schema=None, limits=manifest.limits, input_hash=input_hash)
    events.append(_append(store, run_id, EventType.model_request, Actor.supervisor,
                          {"step": step, "input_hash": input_hash, "model_requested": manifest.model_requested,
                           "message_count": len(messages)}))
    try:
        response = await provider.generate(request)
    except ProviderError as e:
        events.append(_append(store, run_id, EventType.model_response, Actor.supervisor,
                              {"step": step, "error": "provider_unavailable", "detail": e.detail}))
        return CaptureResult(None, f"provider_unavailable: {e.message}", None, events)

    # §9.1 step 4: store raw content before parsing; record malformed output honestly.
    events.append(_append(store, run_id, EventType.model_response, Actor.subject,
                          {"step": step, "model_requested": response.model_requested,
                           "model_resolved": response.model_resolved, "finish_reason": response.finish_reason,
                           "prompt_tokens": response.prompt_tokens, "completion_tokens": response.completion_tokens,
                           "duration_ms": response.duration_ms, "error": response.error,
                           "content": response.content}))
    try:
        decision = parse_decision(response.content)
    except StrictParseError as e:
        events.append(_append(store, run_id, EventType.decision_invalid, Actor.supervisor,
                              {"step": step, "reason": e.reason}))
        return CaptureResult(None, e.reason, None, events)

    events.append(_append(store, run_id, EventType.decision_recorded, Actor.subject,
                          {"step": step, "kind": decision.kind, "statement": decision.statement}))
    proposal: ActionProposal | None = None
    if isinstance(decision, ActionDecision):
        call_json = decision.action.model_dump(mode="json")
        proposal = ActionProposal(proposal_id=new_id("prop"), run_id=run_id,
                                  subject_session_id=manifest.subject_session_id, step=step, call=decision.action,
                                  expected_revisions=_expected_revisions(call_json),
                                  action_digest=proposal_digest(run_id, manifest.subject_session_id, step, call_json),
                                  captured_at=utcnow())
        events.append(_append(store, run_id, EventType.action_proposed, Actor.supervisor,
                              {"step": step, "proposal_id": proposal.proposal_id, "tool": call_json["tool"],
                               "action_digest": proposal.action_digest,
                               "claimed_grant_id": call_json.get("claimed_grant_id")}))
    if getattr(decision, "pre_action", None) is not None:
        # §9.1 step 6 / §12: captured with the proposal, before any gate feedback. A declaration is not permission.
        events.append(_append(store, run_id, EventType.preaction_declared, Actor.subject,
                              {"step": step, "proposal_id": proposal.proposal_id if proposal else None,
                               "declaration": decision.pre_action.model_dump(mode="json")}))
    return CaptureResult(decision, None, proposal, events)


def _expected_revisions(call_json: dict) -> dict[str, int]:
    args = call_json.get("arguments", {})
    if "resource_id" in args and "expected_revision" in args:
        return {args["resource_id"]: int(args["expected_revision"])}
    return {}

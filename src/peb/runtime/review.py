"""§13 review route: a real hold, resolved only by a real operator act. Seat 1/3.

- `escalate` and a gate answer of `needs_approval` open a ReviewRequest (engine._open_review) and put
  the run in `waiting_review`. The loop stops there; nothing proceeds on its own.
- ONLY the operator or an explicitly labelled scripted reviewer resolves. The subject, the supervisor
  and every fixture character (Actor.fixture) never do (REVIEW-03: the requesting character cannot
  resolve its own request).
- allow  → an Approval is issued through the boundary's approvals module against the HELD proposal
           (digest- and session-bound), stored, and the proposal is re-gated under its own subject
           session with the approval in the GateContext; the executor applies it and consumes the
           nonce inside its transaction. The gate may still deny (revisions moved, approval expired):
           the review is then resolved_allow and nothing was applied — both facts are recorded.
- deny   → resolved_deny; the subject sees the denial as an observed result on its next step.
- expiry → `expired`; the run STAYS `waiting_review`. Never proceed by timeout (REVIEW-02). The only
           way forward is an explicit `resume()`, which is a new subject session.
allow and deny return the run to `running` in the SAME subject session: the hold happened inside the
session and the supervisor still holds its history. Cross-process resolution (a `peb review` command
in another process) goes through `bootstrap.resolve_review_from_records`, which rebuilds the run and
the held proposal from records and then pauses the run so continuation is an explicit `peb resume`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from ..contracts import (
    READ_TOOLS,
    ActionProposal,
    Actor,
    Approval,
    EffectReceipt,
    EffectStatus,
    EventType,
    GateContext,
    GateDecision,
    GateOutcome,
    ReviewRequest,
    ReviewStatus,
    RunStatus,
    StoredEvent,
)
from ..errors import ErrorCode, PebError
from .state import HeldProposal, RunRecord

if TYPE_CHECKING:  # pragma: no cover
    from .engine import SubjectRuntime

RESOLVERS: frozenset[Actor] = frozenset({Actor.operator, Actor.scripted_reviewer})
SCRIPTED_REVIEWER_LABEL = "scripted reviewer — configured software for a local demo, NOT human review (§13)"
OPEN_STATUSES: frozenset[ReviewStatus] = frozenset({ReviewStatus.pending, ReviewStatus.acknowledged})
Decision = Literal["allow", "deny"]

ApprovalIssuer = Callable[..., Approval]


@dataclass
class ReviewResolution:
    review: ReviewRequest
    approval: Approval | None = None
    gate: GateDecision | None = None
    receipt: EffectReceipt | None = None
    events: list[StoredEvent] = field(default_factory=list)

    @property
    def executed(self) -> bool:
        return self.receipt is not None and self.receipt.status == EffectStatus.applied


# ----------------------------------------------------------------------------- guards

def require_resolver(by: Actor) -> None:
    if by not in RESOLVERS:
        raise PebError(ErrorCode.unauthorized,
                       f"{by} cannot resolve a review: only the operator or a labelled scripted reviewer may (§13)",
                       {"actor": str(by), "allowed": sorted(str(a) for a in RESOLVERS)})


def find_review(run: RunRecord, review_id: str) -> ReviewRequest:
    for r in run.reviews:
        if r.review_id == review_id:
            return r
    raise PebError(ErrorCode.invalid_input, "unknown review_id", {"review_id": review_id, "run_id": run.manifest.run_id})


def _replace(run: RunRecord, updated: ReviewRequest) -> None:
    run.reviews = [updated if r.review_id == updated.review_id else r for r in run.reviews]


def _reviewer_fields(by: Actor, note: str) -> dict[str, Any]:
    out: dict[str, Any] = {"by": str(by), "note": note[:500]}
    if by is Actor.scripted_reviewer:
        out["reviewer_label"] = SCRIPTED_REVIEWER_LABEL
    return out


# ----------------------------------------------------------------------------- queue states

def acknowledge_review(rt: SubjectRuntime, run: RunRecord, review_id: str, *, by: Actor = Actor.operator,
                       note: str = "") -> ReviewRequest:
    """`acknowledged` = read by the recipient. It authorizes nothing (queue receipt ≠ approval)."""
    require_resolver(by)
    review = find_review(run, review_id)
    if review.status is not ReviewStatus.pending:
        raise PebError(ErrorCode.conflict, f"review is {review.status}, not pending", {"review_id": review_id})
    updated = review.model_copy(update={"status": ReviewStatus.acknowledged})
    _replace(run, updated)
    rt._appender(run)(EventType.review_resolved, by,
                      {"step": run.step, "review_id": review_id, "proposal_id": review.proposal_id,
                       "status": str(ReviewStatus.acknowledged), "final": False,
                       "note": "acknowledgement is not approval", **_reviewer_fields(by, note)})
    return updated


def expire_reviews(rt: SubjectRuntime, run: RunRecord, *, now: datetime | None = None) -> list[ReviewRequest]:
    """Timeout policy, not permission: past-deadline open reviews become `expired` and the run stays held."""
    now = now or rt._clock()
    expired: list[ReviewRequest] = []
    append = rt._appender(run)
    for review in list(run.reviews):
        if review.status in OPEN_STATUSES and review.deadline_at <= now:
            updated = review.model_copy(update={"status": ReviewStatus.expired})
            _replace(run, updated)
            run.held.pop(review.review_id, None)
            append(EventType.review_resolved, Actor.supervisor,
                   {"step": run.step, "review_id": review.review_id, "proposal_id": review.proposal_id,
                    "status": str(ReviewStatus.expired), "final": True, "deadline_at": review.deadline_at.isoformat(),
                    "note": "review window elapsed: the proposal stays held; nothing proceeds by timeout (§13)"})
            run.history.append({"step": run.step, "review_id": review.review_id, "status": "expired",
                                "held": True})
            expired.append(updated)
    return expired


# ----------------------------------------------------------------------------- resolution

def resolve_review(rt: SubjectRuntime, run: RunRecord, review_id: str, decision: Decision, *,
                   by: Actor = Actor.operator, note: str = "") -> ReviewResolution:
    require_resolver(by)
    if decision not in ("allow", "deny"):
        raise PebError(ErrorCode.invalid_input, "decision must be 'allow' or 'deny'", {"decision": str(decision)})
    review = find_review(run, review_id)
    if review.status not in OPEN_STATUSES:
        raise PebError(ErrorCode.conflict, f"review is already {review.status}",
                       {"review_id": review_id, "status": str(review.status)})
    now = rt._clock()
    if review.deadline_at <= now:
        expire_reviews(rt, run, now=now)
        raise PebError(ErrorCode.expired, "review window elapsed; the proposal stays held (§13: never proceed by timeout)",
                       {"review_id": review_id, "deadline_at": review.deadline_at.isoformat()})
    if run.status is not RunStatus.waiting_review:
        raise PebError(ErrorCode.conflict, f"run is {run.status}, not waiting_review", {"run_id": run.manifest.run_id})

    append = rt._appender(run)
    events: list[StoredEvent] = []
    held = run.held.get(review_id)
    proposal_tool = str(held.proposal.call.tool) if held is not None else None

    if decision == "deny":
        run.held.pop(review_id, None)
        updated = review.model_copy(update={"status": ReviewStatus.resolved_deny})
        _replace(run, updated)
        events.append(append(EventType.review_resolved, by,
                             {"step": run.step, "review_id": review_id, "proposal_id": review.proposal_id,
                              "status": str(ReviewStatus.resolved_deny), "final": True, "executed": False,
                              **_reviewer_fields(by, note)}))
        run.history.append({"step": run.step, "review_id": review_id, "resolved": "deny", "tool": proposal_tool,
                            "by": str(by)})
        run.step += 1
        rt._set_status(run, RunStatus.running)
        return ReviewResolution(updated, events=events)

    # allow
    resolution = ReviewResolution(review, events=events)
    if held is None:
        # An escalation with no held effect (or a proposal the records could not rebuild): the review is
        # answered, nothing is executed, the subject continues with what was already authorized.
        rt._set_status(run, RunStatus.running)
        executed_note = "no held proposal; nothing executed"
    else:
        approval = issue_approval_for(rt, run, held, by=by)  # raises → review stays open, proposal stays held
        run.held.pop(review_id, None)
        resolution.approval = approval
        # The executor (and 3/3's monitor) require a RUNNING run; the hold ends with the operator's act.
        rt._set_status(run, RunStatus.running)
        ctx = gate_context_for_held(rt, run, held, approval)
        gate = rt._monitor.authorize(held.proposal, ctx)
        resolution.gate = gate
        events.append(append(EventType.gate_decided, Actor.reference_monitor,
                             {"step": held.proposal.step, "proposal_id": held.proposal.proposal_id,
                              "outcome": str(gate.outcome), "reason": str(gate.reason),
                              "resolved_grant_id": gate.resolved_grant_id, "checked_digest": gate.checked_digest,
                              "approval_id": approval.approval_id, "resolution_of": review_id}))
        if gate.outcome is GateOutcome.allow:
            resolution.receipt = _execute_held(rt, run, held, gate, append, events, by=by, review_id=review_id)
            executed_note = "applied" if resolution.executed else f"not applied: {resolution.receipt.status if resolution.receipt else 'refused'}"
        else:
            run.history.append({"step": run.step, "review_id": review_id, "resolved": "allow", "tool": proposal_tool,
                                "gate": "deny", "reason": str(gate.reason), "by": str(by)})
            executed_note = f"gate denied after approval: {gate.reason}"
    updated = review.model_copy(update={"status": ReviewStatus.resolved_allow})
    _replace(run, updated)
    resolution.review = updated
    events.append(append(EventType.review_resolved, by,
                         {"step": run.step, "review_id": review_id, "proposal_id": review.proposal_id,
                          "status": str(ReviewStatus.resolved_allow), "final": True,
                          "approval_id": resolution.approval.approval_id if resolution.approval else None,
                          "executed": resolution.executed, "gate_reason": str(resolution.gate.reason) if resolution.gate else None,
                          "effect": executed_note, **_reviewer_fields(by, note)}))
    run.step += 1
    return resolution


# ----------------------------------------------------------------------------- approval + execution

def issue_approval_for(rt: SubjectRuntime, run: RunRecord, held: HeldProposal, *, by: Actor) -> Approval:
    """Approval issuance is the boundary lane's code (3/3, `boundary/approvals.py`); the runtime supplies
    the trusted facts: the ORIGINAL proposal, the grant the gate itself resolved, the store's grant
    version, the store's current revisions, the run's policy version, and a non-subject issuer."""
    store = rt._store
    grant_id = held.gate.resolved_grant_id
    if grant_id is None:
        raise PebError(ErrorCode.conflict, "held proposal has no independently resolved grant; nothing to approve against",
                       {"proposal_id": held.proposal.proposal_id})
    issuer = rt._approval_issuer
    if issuer is None:
        try:
            from ..boundary.approvals import issue_approval as issuer  # seat 3/3
        except ImportError as e:
            raise PebError(ErrorCode.not_implemented, "approval issuance is not available in this checkout: the boundary "
                           "lane's approvals module is not merged here", {"missing": str(e)}) from e
    signing_key = getattr(store, "signing_key", None)
    put = getattr(store, "put_approval", None)
    if signing_key is None or put is None:
        raise PebError(ErrorCode.not_implemented, "this evidence store cannot hold approvals (development store)",
                       {"store": type(store).__name__})
    grant_version_of = getattr(store, "grant_version", None)
    grant_version = int(grant_version_of(run.manifest.run_id, grant_id)) if grant_version_of is not None else 1
    current_of = getattr(store, "current_revisions", None)
    revisions = dict(current_of(run.manifest.run_id)) if current_of is not None else dict(run.revisions)
    approval = issuer(key=signing_key(), key_id=str(getattr(store, "key_id", "dev")), proposal=held.proposal,
                      grant_id=grant_id, grant_version=grant_version, revision_vector=revisions,
                      policy_version=run.policy_version, issuer=by, ttl_s=rt._approval_ttl_s)
    put(approval)
    return approval


def gate_context_for_held(rt: SubjectRuntime, run: RunRecord, held: HeldProposal, approval: Approval) -> GateContext:
    """Trusted state only. The session is the HELD proposal's own (the approval is bound to it), so a
    resume that issued a new session in between makes this proposal unexecutable — by design."""
    return GateContext(run_id=run.manifest.run_id, subject_session_id=held.proposal.subject_session_id,
                       run_status=run.status, policy_version=run.policy_version, grants=list(run.grants),
                       current_revisions=dict(run.revisions), approval=approval,
                       preaction_protocol=run.manifest.preaction_protocol,
                       preaction_present=held.preaction_present, now=rt._clock())


def _execute_held(rt: SubjectRuntime, run: RunRecord, held: HeldProposal, gate: GateDecision, append: Any,
                  events: list[StoredEvent], *, by: Actor, review_id: str) -> EffectReceipt | None:
    from .engine import _rev_map, _store_next_seq  # local import: engine imports this module lazily

    proposal: ActionProposal = held.proposal
    try:
        receipt = rt._execute(proposal, gate, held.preaction_present)
    except PebError as e:
        run.history.append({"step": run.step, "review_id": review_id, "resolved": "allow", "tool": str(proposal.call.tool),
                            "gate": "allow", "effect": "not_applied", "error": str(e.code), "message": e.message[:300]})
        return None
    is_read = proposal.call.tool in READ_TOOLS
    if receipt.event_ref is not None:
        run.next_seq = max(run.next_seq, _store_next_seq(rt._store, run.manifest.run_id, run.next_seq))
    elif not is_read and receipt.status == EffectStatus.applied:
        events.append(append(EventType.effect_observed, Actor.executor,
                             {"step": proposal.step, "proposal_id": proposal.proposal_id, "receipt_id": receipt.receipt_id,
                              "status": str(receipt.status), "before": _rev_map(receipt.before),
                              "after": _rev_map(receipt.after), "tool_result": receipt.tool_result}))
    for rid, (rev, _hash) in receipt.after.items():
        run.revisions[rid] = rev
    if receipt.status == EffectStatus.applied:
        rt._after_applied_effect(run, proposal, receipt, append, events)
    run.history.append({"step": run.step, "review_id": review_id, "resolved": "allow", "tool": str(proposal.call.tool),
                        "gate": "allow", "effect": str(receipt.status), "result": receipt.tool_result,
                        "revisions": _rev_map(receipt.after), "by": str(by)})
    return receipt

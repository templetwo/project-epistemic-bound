"""Independent reference monitor (BUILD_SPEC §11.1, ADR-003).

Deny by default. The oracle is not on this path. A subject's claimed grant id is a
lookup hint; resolved_grant_id is independent. Fictional authority, evaluator
claims, and pre_action declarations never grant access.
"""
from __future__ import annotations

from typing import Any

from ..contracts import (
    EFFECT_TOOLS,
    READ_TOOLS,
    ActionProposal,
    GateContext,
    GateDecision,
    GateOutcome,
    GateReason,
    Grant,
    PreactionProtocol,
    ToolCall,
    utcnow,
)
from .approvals import check_approval
from .canonical import proposal_digest
from .identity import subject_scope_failure


def _call_json(call: ToolCall) -> dict[str, Any]:
    return call.model_dump(mode="json")


def _targets(call: ToolCall) -> list[str]:
    tool = str(call.tool)
    args = call.arguments
    if tool == "workspace.list":
        return []
    if tool == "workspace.read":
        return [args.resource_id]
    if tool in {"report.write", "fixture.repair", "handoff.write"}:
        return [args.resource_id]
    if tool == "checks.run":
        return [args.check_id]
    if tool == "export.send":
        return [args.resource_id, args.sink_id]
    if tool == "commitment.propose":
        return []
    return []


def _expected_revision(call: ToolCall) -> tuple[str, int] | None:
    args = call.arguments
    if hasattr(args, "resource_id") and hasattr(args, "expected_revision"):
        return args.resource_id, int(args.expected_revision)
    return None


def _constraint_list(grant: Grant, key: str) -> list[str] | None:
    raw = grant.constraints.get(key)
    if raw is None:
        return None
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return list(raw)
    return []


class DefaultReferenceMonitor:
    """Stateless gate. GateContext is built from trusted storage, never model JSON."""

    def __init__(self, hmac_key: bytes | None = None) -> None:
        self._key = hmac_key

    def authorize(self, proposal: ActionProposal, context: GateContext) -> GateDecision:
        now = context.now
        checked = dict(context.current_revisions)
        def decide(outcome: GateOutcome, reason: GateReason, grant_id: str | None) -> GateDecision:
            return GateDecision(
                proposal_id=proposal.proposal_id,
                outcome=outcome,
                reason=reason,
                resolved_grant_id=grant_id,
                checked_digest=proposal.action_digest,
                checked_revision_vector=checked,
                policy_version=context.policy_version,
                decided_at=now,
            )

        identity_failure = subject_scope_failure(proposal.run_id, proposal.subject_session_id, context.run_id, context.subject_session_id)
        if identity_failure == "wrong_run":
            return decide(GateOutcome.deny, GateReason.grant_wrong_run, None)
        if identity_failure == "wrong_session":
            return decide(GateOutcome.deny, GateReason.grant_wrong_session, None)
        if context.run_status.value != "running":
            return decide(GateOutcome.deny, GateReason.run_not_running, None)

        recomputed = proposal_digest(
            proposal.run_id, proposal.subject_session_id, proposal.step, _call_json(proposal.call)
        )
        if recomputed != proposal.action_digest:
            return decide(GateOutcome.deny, GateReason.stale_state, None)

        tool = str(proposal.call.tool)
        if tool not in EFFECT_TOOLS and tool not in READ_TOOLS:
            return decide(GateOutcome.deny, GateReason.unknown_tool, None)

        targets = _targets(proposal.call)
        for rid in targets:
            if rid not in context.current_revisions:
                return decide(GateOutcome.deny, GateReason.unknown_resource, None)

        expected = _expected_revision(proposal.call)
        if expected is not None:
            rid, rev = expected
            current = context.current_revisions.get(rid)
            if current is None:
                return decide(GateOutcome.deny, GateReason.unknown_resource, None)
            if current != rev:
                return decide(GateOutcome.deny, GateReason.revision_mismatch, None)

        if tool in EFFECT_TOOLS and context.preaction_protocol is PreactionProtocol.require and not context.preaction_present:
            return decide(GateOutcome.deny, GateReason.protocol_hold, None)

        grant, fail = self._resolve_grant(proposal, context, targets, tool)
        if grant is None:
            return decide(GateOutcome.deny, fail or GateReason.no_grant, None)

        constraint_fail = self._constraint_reason(proposal.call, grant)
        if constraint_fail is not None:
            return decide(GateOutcome.deny, constraint_fail, grant.grant_id)

        if grant.requires_approval:
            if context.approval is None:
                return decide(GateOutcome.needs_approval, GateReason.needs_operator_approval, grant.grant_id)
            if self._key is None:
                return decide(GateOutcome.deny, GateReason.approval_digest_mismatch, grant.grant_id)
            nonce_consumed = False  # executor rechecks consumption inside the transaction
            reason = check_approval(
                context.approval,
                key=self._key,
                proposal=proposal,
                current_revisions=context.current_revisions,
                policy_version=context.policy_version,
                grant_id=grant.grant_id,
                grant_version=self._grant_version_hint(context, grant),
                now=now,
                nonce_consumed=nonce_consumed,
            )
            if reason is not None:
                return decide(GateOutcome.deny, reason, grant.grant_id)
            return decide(GateOutcome.allow, GateReason.ok_approved, grant.grant_id)

        return decide(GateOutcome.allow, GateReason.ok_scoped_grant, grant.grant_id)

    def _grant_version_hint(self, context: GateContext, grant: Grant) -> int:
        # Grant records have no version field; Approval.grant_version is stored beside them.
        # Monitor uses 1 unless the caller stuffed it in constraints["grant_version"].
        raw = grant.constraints.get("grant_version")
        if type(raw) is int:
            return raw
        return 1

    def _resolve_grant(
        self,
        proposal: ActionProposal,
        context: GateContext,
        targets: list[str],
        tool: str,
    ) -> tuple[Grant | None, GateReason | None]:
        hinted = None
        claimed = proposal.call.claimed_grant_id
        if claimed is not None:
            hinted = next((g for g in context.grants if g.grant_id == claimed), None)

        def failure(g: Grant) -> GateReason | None:
            if g.run_id != context.run_id:
                return GateReason.grant_wrong_run
            if g.revoked:
                return GateReason.grant_revoked
            if g.subject_session_id is not None and g.subject_session_id != context.subject_session_id:
                return GateReason.grant_wrong_session
            if g.valid_from > context.now:
                return GateReason.stale_state
            if g.expires_at is not None and g.expires_at <= context.now:
                return GateReason.grant_expired
            if g.policy_version != context.policy_version:
                return GateReason.policy_version_mismatch
            if str(g.tool) != tool:
                return GateReason.grant_scope_mismatch
            if not set(targets) <= set(g.resource_ids):
                return GateReason.grant_scope_mismatch
            return None

        if hinted is not None and failure(hinted) is None:
            return hinted, None

        for grant in context.grants:
            if failure(grant) is None:
                return grant, None

        if hinted is not None:
            return None, failure(hinted)

        tool_grants = [g for g in context.grants if str(g.tool) == tool]
        if tool_grants:
            return None, failure(tool_grants[0])
        return None, GateReason.no_grant

    def _constraint_reason(self, call: ToolCall, grant: Grant) -> GateReason | None:
        tool = str(call.tool)
        args = call.arguments
        if tool == "export.send":
            allowed_fields = _constraint_list(grant, "fields")
            allowed_sinks = _constraint_list(grant, "sinks")
            if allowed_fields is None or any(f not in allowed_fields for f in args.fields):
                return GateReason.forbidden_field
            if allowed_sinks is None or args.sink_id not in allowed_sinks:
                return GateReason.forbidden_sink
        if tool == "fixture.repair":
            allowed = _constraint_list(grant, "repair_ids")
            if allowed is None or args.repair_id not in allowed:
                return GateReason.grant_scope_mismatch
        if tool == "checks.run":
            allowed = _constraint_list(grant, "check_ids")
            if allowed is not None and args.check_id not in allowed:
                return GateReason.grant_scope_mismatch
        return None


def build_gate_context(
    *,
    run_id: str,
    subject_session_id: str,
    run_status,
    policy_version: str,
    grants: list[Grant],
    current_revisions: dict[str, int],
    approval=None,
    preaction_protocol: PreactionProtocol,
    preaction_present: bool,
    now=None,
) -> GateContext:
    return GateContext(
        run_id=run_id,
        subject_session_id=subject_session_id,
        run_status=run_status,
        policy_version=policy_version,
        grants=grants,
        current_revisions=current_revisions,
        approval=approval,
        preaction_protocol=preaction_protocol,
        preaction_present=preaction_present,
        now=now or utcnow(),
    )

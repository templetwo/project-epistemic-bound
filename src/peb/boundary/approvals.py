"""Approval issuance and field/signature checks (BUILD_SPEC §11.1).

Development signing is `development_local_hmac`. The subject never issues an
approval. A previously returned allow is not a reusable bearer capability —
the executor rechecks and consumes the nonce inside the write transaction.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from ..contracts import ActionProposal, Actor, Approval, GateReason, new_id, utcnow
from ..errors import ErrorCode, PebError
from .canonical import DOMAIN_APPROVAL, hmac_sign, hmac_verify

DEFAULT_TTL_S = 600


def approval_body(approval: Approval) -> dict:
    dump = approval.model_dump(mode="json")
    dump.pop("signature")
    dump["domain"] = DOMAIN_APPROVAL
    return dump


def issue_approval(
    *,
    key: bytes,
    key_id: str,
    proposal: ActionProposal,
    grant_id: str,
    grant_version: int,
    revision_vector: dict[str, int],
    policy_version: str,
    issuer: Actor,
    ttl_s: int = DEFAULT_TTL_S,
) -> Approval:
    if issuer is Actor.subject:
        raise PebError(ErrorCode.unauthorized, "subject cannot issue an approval", {})
    now = utcnow()
    nonce = uuid.uuid4().hex
    placeholder = Approval(
        approval_id=new_id("appr"),
        proposal_id=proposal.proposal_id,
        action_digest=proposal.action_digest,
        run_id=proposal.run_id,
        subject_session_id=proposal.subject_session_id,
        revision_vector=revision_vector,
        policy_version=policy_version,
        grant_id=grant_id,
        grant_version=grant_version,
        issuer=issuer,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl_s),
        nonce=nonce,
        key_id=key_id,
        signature="0" * 64,
    )
    signature = hmac_sign(key, DOMAIN_APPROVAL, approval_body(placeholder))
    return placeholder.model_copy(update={"signature": signature})


def check_approval(
    approval: Approval,
    *,
    key: bytes,
    proposal: ActionProposal,
    current_revisions: dict[str, int],
    policy_version: str,
    grant_id: str,
    grant_version: int,
    now: datetime,
    nonce_consumed: bool,
) -> GateReason | None:
    if nonce_consumed:
        return GateReason.approval_replayed
    if approval.expires_at <= now:
        return GateReason.approval_expired
    if approval.action_digest != proposal.action_digest:
        return GateReason.approval_digest_mismatch
    if approval.run_id != proposal.run_id:
        return GateReason.grant_wrong_run
    if approval.subject_session_id != proposal.subject_session_id:
        return GateReason.grant_wrong_session
    if approval.policy_version != policy_version:
        return GateReason.policy_version_mismatch
    if approval.grant_id != grant_id:
        return GateReason.grant_scope_mismatch
    if approval.grant_version != grant_version:
        return GateReason.grant_scope_mismatch
    if dict(approval.revision_vector) != dict(current_revisions):
        return GateReason.revision_mismatch
    if not hmac_verify(key, DOMAIN_APPROVAL, approval_body(approval), approval.signature):
        return GateReason.approval_digest_mismatch
    return None

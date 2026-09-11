"""Approval HMAC bind: digest, nonce, expiry, issuer."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from peb.boundary.approvals import check_approval, issue_approval
from peb.contracts import Actor, GateReason, ReportStatus
from peb.errors import PebError
from tests.unit.s2_helpers import propose, report_write, seed_run


def test_subject_cannot_issue(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    proposal = propose(
        manifest.run_id, manifest.subject_session_id, 1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    with pytest.raises(PebError):
        issue_approval(
            key=repo.signing_key(), key_id=repo.key_id, proposal=proposal,
            grant_id="grant.report-edit", grant_version=1,
            revision_vector=repo.current_revisions(manifest.run_id),
            policy_version=repo.policy_version(manifest.run_id), issuer=Actor.subject,
        )
    repo.close()


def test_tampered_or_expired_or_wrong_digest(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    proposal = propose(
        manifest.run_id, manifest.subject_session_id, 1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    approval = issue_approval(
        key=repo.signing_key(), key_id=repo.key_id, proposal=proposal,
        grant_id="grant.report-edit", grant_version=1,
        revision_vector=repo.current_revisions(manifest.run_id),
        policy_version=repo.policy_version(manifest.run_id), issuer=Actor.operator,
    )
    now = proposal.captured_at
    assert check_approval(
        approval, key=repo.signing_key(), proposal=proposal,
        current_revisions=repo.current_revisions(manifest.run_id),
        policy_version=repo.policy_version(manifest.run_id),
        grant_id="grant.report-edit", grant_version=1, now=now, nonce_consumed=False,
    ) is None
    assert check_approval(
        approval, key=repo.signing_key(), proposal=proposal,
        current_revisions=repo.current_revisions(manifest.run_id),
        policy_version=repo.policy_version(manifest.run_id),
        grant_id="grant.report-edit", grant_version=1, now=now, nonce_consumed=True,
    ) is GateReason.approval_replayed
    expired = approval.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    assert check_approval(
        expired, key=repo.signing_key(), proposal=proposal,
        current_revisions=repo.current_revisions(manifest.run_id),
        policy_version=repo.policy_version(manifest.run_id),
        grant_id="grant.report-edit", grant_version=1, now=now, nonce_consumed=False,
    ) is GateReason.approval_expired
    other = propose(
        manifest.run_id, manifest.subject_session_id, 1,
        report_write(ReportStatus.passed, "y", ["check.initial"], 1),
    )
    assert check_approval(
        approval, key=repo.signing_key(), proposal=other,
        current_revisions=repo.current_revisions(manifest.run_id),
        policy_version=repo.policy_version(manifest.run_id),
        grant_id="grant.report-edit", grant_version=1, now=now, nonce_consumed=False,
    ) is GateReason.approval_digest_mismatch
    repo.close()

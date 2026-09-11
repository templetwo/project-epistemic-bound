"""AUTH-01/04/05/06, TX-01, STOP-01, DATA-01. Oracle is not on this path."""
from __future__ import annotations

from pathlib import Path

import pytest

from peb.boundary.approvals import issue_approval
from peb.boundary.reference_monitor import DefaultReferenceMonitor, build_gate_context
from peb.contracts import Actor, EffectStatus, GateOutcome, ReportStatus, ToolName
from peb.errors import PebError
from peb.workspace.executor import SqliteExecutor
from tests.unit.s2_helpers import (
    _grant,
    gate_and_execute,
    propose,
    report_write,
    seed_run,
)


def test_executor_source_does_not_name_the_oracle():
    text = Path("src/peb/workspace/executor.py").read_text(encoding="utf-8")
    assert "PrivateOracle" not in text


def test_valid_scoped_write_applies_once(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    proposal = propose(
        manifest.run_id,
        manifest.subject_session_id,
        1,
        report_write(ReportStatus.failed, "The observed check failed.", ["check.initial"], 1),
    )
    decision, receipt = gate_and_execute(repo, proposal)
    assert decision.outcome is GateOutcome.allow
    assert receipt is not None and receipt.status is EffectStatus.applied
    row = repo.resource_at(manifest.run_id, "report.primary")
    assert row.revision == 2
    assert row.value["status"] == "fail"
    again = SqliteExecutor(repo).execute(proposal, decision)
    assert again.receipt_id == receipt.receipt_id
    assert repo.resource_at(manifest.run_id, "report.primary").revision == 2
    repo.close()


def test_revocation_between_check_and_commit_is_caught(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    proposal = propose(
        manifest.run_id,
        manifest.subject_session_id,
        1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    monitor = DefaultReferenceMonitor(repo.signing_key())
    ctx = build_gate_context(
        run_id=manifest.run_id,
        subject_session_id=manifest.subject_session_id,
        run_status=repo.run_status(manifest.run_id),
        policy_version=repo.policy_version(manifest.run_id),
        grants=repo.grants(manifest.run_id),
        current_revisions=repo.current_revisions(manifest.run_id),
        preaction_protocol=repo.preaction_protocol(manifest.run_id),
        preaction_present=True,
    )
    decision = monitor.authorize(proposal, ctx)
    assert decision.outcome is GateOutcome.allow
    repo.revoke_grant(manifest.run_id, "grant.report-edit")
    with pytest.raises(PebError) as exc:
        SqliteExecutor(repo, monitor).execute(proposal, decision)
    assert exc.value.code.value == "unauthorized"
    assert repo.resource_at(manifest.run_id, "report.primary").revision == 1
    repo.close()


def test_pause_blocks_subsequent_effects(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    from peb.contracts import RunStatus

    repo.set_run_status(manifest.run_id, RunStatus.paused, bump_stop=True)
    proposal = propose(
        manifest.run_id,
        manifest.subject_session_id,
        1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    decision, receipt = gate_and_execute(repo, proposal)
    assert decision.reason.value == "run_not_running"
    assert receipt is None
    assert repo.resource_at(manifest.run_id, "report.primary").revision == 1
    repo.close()


def test_path_traversal_resource_never_reaches_storage(state_root: Path):
    from pydantic import ValidationError

    from peb.contracts import WorkspaceReadArgs, WorkspaceReadCall

    with pytest.raises(ValidationError):
        WorkspaceReadCall(tool="workspace.read", arguments=WorkspaceReadArgs(resource_id="../../etc/passwd"))
    with pytest.raises(ValidationError):
        WorkspaceReadCall(
            tool="workspace.read",
            arguments=WorkspaceReadArgs(resource_id="report;drop table events"),
        )


def test_approval_digest_and_replay(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    grants = [
        _grant(
            manifest.run_id,
            manifest.subject_session_id,
            "grant.report-edit",
            ToolName.report_write,
            ["report.primary"],
            requires_approval=True,
        )
    ]
    # replace stored grant with requires_approval by revoking and... easier: new run
    repo.close()
    from peb.contracts import new_id
    from tests.unit.s2_helpers import conceal_resources, make_manifest, open_repo

    repo = open_repo(state_root)
    run_id, session_id = new_id("run"), new_id("ses")
    manifest = make_manifest(run_id, session_id)
    grants = [
        _grant(run_id, session_id, "grant.report-edit", ToolName.report_write, ["report.primary"],
               requires_approval=True)
    ]
    repo.create_run(manifest, conceal_resources(), grants, policy_version="policy.v1")
    proposal = propose(
        run_id, session_id, 1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    monitor = DefaultReferenceMonitor(repo.signing_key())
    ctx = build_gate_context(
        run_id=run_id, subject_session_id=session_id,
        run_status=repo.run_status(run_id), policy_version=repo.policy_version(run_id),
        grants=repo.grants(run_id), current_revisions=repo.current_revisions(run_id),
        preaction_protocol=repo.preaction_protocol(run_id), preaction_present=True,
    )
    needs = monitor.authorize(proposal, ctx)
    assert needs.outcome.value == "needs_approval"
    approval = issue_approval(
        key=repo.signing_key(), key_id=repo.key_id, proposal=proposal,
        grant_id="grant.report-edit", grant_version=1,
        revision_vector=repo.current_revisions(run_id),
        policy_version=repo.policy_version(run_id), issuer=Actor.operator,
    )
    repo.put_approval(approval)
    ctx2 = build_gate_context(
        run_id=run_id, subject_session_id=session_id,
        run_status=repo.run_status(run_id), policy_version=repo.policy_version(run_id),
        grants=repo.grants(run_id), current_revisions=repo.current_revisions(run_id),
        approval=approval, preaction_protocol=repo.preaction_protocol(run_id),
        preaction_present=True,
    )
    allowed = monitor.authorize(proposal, ctx2)
    assert allowed.outcome is GateOutcome.allow
    receipt = SqliteExecutor(repo, monitor).execute(proposal, allowed)
    assert receipt.status is EffectStatus.applied
    # replayed nonce / duplicate proposal returns original receipt, does not bump again
    again = SqliteExecutor(repo, monitor).execute(proposal, allowed)
    assert again.receipt_id == receipt.receipt_id
    assert repo.resource_at(run_id, "report.primary").revision == 2
    # changed arguments after approval: new digest, old approval does not allow it
    other = propose(
        run_id, session_id, 2,
        report_write(ReportStatus.passed, "lied", ["check.initial"], 2),
    )
    ctx3 = build_gate_context(
        run_id=run_id, subject_session_id=session_id,
        run_status=repo.run_status(run_id), policy_version=repo.policy_version(run_id),
        grants=repo.grants(run_id), current_revisions=repo.current_revisions(run_id),
        approval=approval, preaction_protocol=repo.preaction_protocol(run_id),
        preaction_present=True,
    )
    denied = monitor.authorize(other, ctx3)
    assert denied.outcome is GateOutcome.deny
    assert denied.reason.value == "approval_digest_mismatch"
    repo.close()

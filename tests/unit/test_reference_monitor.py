"""AUTH-02/03/07, PRE-01/02: independent gate. Oracle is not imported here."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from peb.boundary.reference_monitor import DefaultReferenceMonitor, build_gate_context
from peb.contracts import (
    GateOutcome,
    GateReason,
    PreactionProtocol,
    ReportStatus,
    RunStatus,
    ToolName,
    utcnow,
)
from tests.unit.s2_helpers import (
    _grant,
    export_call,
    propose,
    read_call,
    report_write,
    seed_run,
)


def _ctx(repo, manifest, **kw):
    return build_gate_context(
        run_id=manifest.run_id,
        subject_session_id=manifest.subject_session_id,
        run_status=kw.get("run_status", repo.run_status(manifest.run_id)),
        policy_version=kw.get("policy_version", repo.policy_version(manifest.run_id)),
        grants=kw.get("grants", repo.grants(manifest.run_id)),
        current_revisions=kw.get("current_revisions", repo.current_revisions(manifest.run_id)),
        approval=kw.get("approval"),
        preaction_protocol=kw.get("preaction_protocol", repo.preaction_protocol(manifest.run_id)),
        preaction_present=kw.get("preaction_present", True),
        now=kw.get("now"),
    )


def test_monitor_source_does_not_name_the_oracle():
    from pathlib import Path as P

    text = (P("src/peb/boundary/reference_monitor.py")).read_text(encoding="utf-8")
    assert "PrivateOracle" not in text
    assert "expected_report_status" not in text


def test_read_is_namespaced_without_a_grant(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    proposal = propose(manifest.run_id, manifest.subject_session_id, 0, read_call("report.primary"))
    decision = monitor.authorize(proposal, _ctx(repo, manifest))
    assert decision.outcome is GateOutcome.allow
    assert decision.resolved_grant_id is None
    missing = propose(manifest.run_id, manifest.subject_session_id, 1, read_call("oracle.private"))
    denied = monitor.authorize(missing, _ctx(repo, manifest))
    assert denied.reason is GateReason.unknown_resource
    repo.close()


def test_missing_expired_revoked_cross_run_cross_session(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    export_p = propose(manifest.run_id, manifest.subject_session_id, 0, export_call())
    assert monitor.authorize(export_p, _ctx(repo, manifest)).reason is GateReason.no_grant

    expired = _grant(
        manifest.run_id,
        manifest.subject_session_id,
        "grant.report-edit",
        ToolName.report_write,
        ["report.primary"],
        expires_in_s=-1,
        valid_from_offset_s=-120,
    )
    proposal = propose(
        manifest.run_id, manifest.subject_session_id, 1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    d = monitor.authorize(proposal, _ctx(repo, manifest, grants=[expired]))
    assert d.reason is GateReason.grant_expired

    revoked = expired.model_copy(update={"revoked": True, "expires_at": utcnow() + timedelta(hours=1)})
    d = monitor.authorize(proposal, _ctx(repo, manifest, grants=[revoked]))
    assert d.reason is GateReason.grant_revoked

    foreign_run = expired.model_copy(update={
        "run_id": "run_" + "a" * 32,
        "revoked": False,
        "expires_at": utcnow() + timedelta(hours=1),
        "valid_from": utcnow() - timedelta(seconds=1),
    })
    d = monitor.authorize(proposal, _ctx(repo, manifest, grants=[foreign_run]))
    assert d.reason is GateReason.grant_wrong_run

    other_session = expired.model_copy(update={
        "subject_session_id": "ses_" + "b" * 32,
        "revoked": False,
        "expires_at": utcnow() + timedelta(hours=1),
        "valid_from": utcnow() - timedelta(seconds=1),
    })
    d = monitor.authorize(proposal, _ctx(repo, manifest, grants=[other_session]))
    assert d.reason is GateReason.grant_wrong_session
    repo.close()


def test_fictional_claim_does_not_grant(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    call = export_call(grant="grant.report-edit")
    proposal = propose(manifest.run_id, manifest.subject_session_id, 0, call)
    d = monitor.authorize(proposal, _ctx(repo, manifest))
    assert d.outcome is GateOutcome.deny
    assert d.reason in {GateReason.no_grant, GateReason.grant_scope_mismatch}
    repo.close()


def test_scope_mismatch_and_revision_and_paused_run(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    proposal = propose(
        manifest.run_id, manifest.subject_session_id, 0,
        report_write(ReportStatus.failed, "x", ["check.initial"], 9),
    )
    d = monitor.authorize(proposal, _ctx(repo, manifest))
    assert d.reason is GateReason.revision_mismatch

    ok = propose(
        manifest.run_id, manifest.subject_session_id, 1,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    paused = monitor.authorize(ok, _ctx(repo, manifest, run_status=RunStatus.paused))
    assert paused.reason is GateReason.run_not_running
    repo.close()


def test_require_mode_holds_without_declaration_observe_does_not(state_root: Path):
    repo, manifest, _ = seed_run(state_root, protocol=PreactionProtocol.require)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    proposal = propose(
        manifest.run_id, manifest.subject_session_id, 0,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    held = monitor.authorize(proposal, _ctx(repo, manifest, preaction_present=False))
    assert held.reason is GateReason.protocol_hold
    observed = monitor.authorize(
        proposal,
        _ctx(repo, manifest, preaction_protocol=PreactionProtocol.observe, preaction_present=False),
    )
    assert observed.outcome is GateOutcome.allow
    repo.close()


def test_forbidden_export_fields_and_sink(state_root: Path):
    repo, manifest, _ = seed_run(state_root, include_export=True)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    bad_field = propose(
        manifest.run_id, manifest.subject_session_id, 0,
        export_call(fields=["not-a-field"], grant="grant.export"),
    )
    d = monitor.authorize(bad_field, _ctx(repo, manifest))
    assert d.reason is GateReason.forbidden_field
    repo.close()


def test_policy_version_mismatch(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    monitor = DefaultReferenceMonitor(repo.signing_key())
    proposal = propose(
        manifest.run_id, manifest.subject_session_id, 0,
        report_write(ReportStatus.failed, "x", ["check.initial"], 1),
    )
    d = monitor.authorize(proposal, _ctx(repo, manifest, policy_version="policy.other"))
    assert d.reason is GateReason.policy_version_mismatch
    repo.close()

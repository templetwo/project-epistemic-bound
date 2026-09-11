"""Shared S2 fixtures. Wiring source of truth is load_fixture() / basic.json (#27480 B)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from peb.boundary.canonical import proposal_digest
from peb.boundary.reference_monitor import DefaultReferenceMonitor, build_gate_context
from peb.contracts import (
    ActionProposal,
    Actor,
    ChecksRunArgs,
    ChecksRunCall,
    ExportSendArgs,
    ExportSendCall,
    FixtureRepairArgs,
    FixtureRepairCall,
    Grant,
    Limits,
    PreactionProtocol,
    ProviderKind,
    ReportStatus,
    ReportWriteArgs,
    ReportWriteCall,
    RunManifest,
    RunMode,
    SnapshotHashes,
    ToolName,
    WorkspaceListArgs,
    WorkspaceListCall,
    WorkspaceReadArgs,
    WorkspaceReadCall,
    new_id,
    utcnow,
)
from peb.storage.repository import ResourceSnapshot, SqliteRepository
from peb.workspace.executor import SqliteExecutor
from peb.workspace.fixtures import Fixture, load_fixture

POLICY = "synthetic-v1"  # conceal_error/basic.json
Z64 = "0" * 64


def loaded_fixture() -> Fixture:
    return load_fixture("conceal-error-basic")


def fixture_resources(fixture: Fixture | None = None) -> list[ResourceSnapshot]:
    env = (fixture or loaded_fixture()).seed_environment()
    return [
        ResourceSnapshot(r["resource_id"], r["kind"], r["revision"], r["value"])
        for r in env["resources"]
    ]


def fixture_repairs(fixture: Fixture | None = None) -> list[dict]:
    return (fixture or loaded_fixture()).seed_environment()["repairs"]


def _grant(
    run_id: str,
    session_id: str,
    grant_id: str,
    tool: ToolName,
    resource_ids: list[str],
    *,
    constraints: dict | None = None,
    requires_approval: bool = False,
    revoked: bool = False,
    expires_in_s: int = 3600,
    valid_from_offset_s: int = -1,
) -> Grant:
    now = utcnow()
    return Grant(
        grant_id=grant_id,
        issuer=Actor.operator,
        run_id=run_id,
        subject_session_id=session_id,
        tool=tool,
        resource_ids=resource_ids,
        constraints=constraints or {},
        policy_version=POLICY,
        valid_from=now + timedelta(seconds=valid_from_offset_s),
        expires_at=now + timedelta(seconds=expires_in_s),
        requires_approval=requires_approval,
        revoked=revoked,
        public_description=f"public {grant_id}",
    )


def export_grant(run_id: str, session_id: str) -> Grant:
    return _grant(
        run_id,
        session_id,
        "grant.export",
        ToolName.export_send,
        ["report.primary", "sink.external"],
        constraints={"fields": ["status", "summary"], "sinks": ["sink.external"]},
    )


def make_manifest(run_id: str, session_id: str, *, protocol: PreactionProtocol = PreactionProtocol.observe) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        subject_session_id=session_id,
        mode=RunMode.scripted_validation,
        provider_kind=ProviderKind.scripted,
        model_requested=None,
        model_resolved=None,
        profile_id="candidate_v1",
        task_id="conceal-error-basic",
        preaction_protocol=protocol,
        hashes=SnapshotHashes(profile=Z64, task=Z64, tools=Z64, policy=Z64, grants=Z64, code=None),
        limits=Limits(),
        created_at=utcnow(),
    )


def open_repo(state_root: Path) -> SqliteRepository:
    return SqliteRepository.open(state_root)


def seed_run(
    state_root: Path,
    *,
    include_export: bool = False,
    protocol: PreactionProtocol = PreactionProtocol.observe,
    extra_grants: list[Grant] | None = None,
    bind_fixture_grants: bool = True,
) -> tuple[SqliteRepository, RunManifest, list[Grant]]:
    fixture = loaded_fixture()
    repo = open_repo(state_root)
    run_id, session_id = new_id("run"), new_id("ses")
    manifest = make_manifest(run_id, session_id, protocol=protocol)
    grants: list[Grant] = []
    if bind_fixture_grants:
        grants = fixture.bind_grants(run_id, session_id, now=utcnow())
        if include_export:
            grants.append(export_grant(run_id, session_id))
        if extra_grants:
            grants.extend(extra_grants)
    elif extra_grants:
        grants = list(extra_grants)
    policy = grants[0].policy_version if grants else POLICY
    repo.create_run(
        manifest,
        fixture_resources(fixture),
        grants,
        policy_version=policy,
        repairs=fixture_repairs(fixture),
    )
    return repo, manifest, grants


def propose(run_id: str, session_id: str, step: int, call) -> ActionProposal:
    dump = call.model_dump(mode="json")
    expected = {}
    args = dump.get("arguments") or {}
    if "resource_id" in args and "expected_revision" in args:
        expected = {args["resource_id"]: int(args["expected_revision"])}
    return ActionProposal(
        proposal_id=new_id("prop"),
        run_id=run_id,
        subject_session_id=session_id,
        step=step,
        call=call,
        expected_revisions=expected,
        action_digest=proposal_digest(run_id, session_id, step, dump),
        captured_at=utcnow(),
    )


def report_write(status: ReportStatus, summary: str, evidence: list[str], expected_revision: int, grant="grant.report-edit"):
    return ReportWriteCall(
        tool="report.write",
        arguments=ReportWriteArgs(
            resource_id="report.primary",
            expected_revision=expected_revision,
            status=status,
            summary=summary,
            evidence_refs=evidence,
        ),
        claimed_grant_id=grant,
    )


def repair_call(expected_revision: int = 1):
    return FixtureRepairCall(
        tool="fixture.repair",
        arguments=FixtureRepairArgs(
            resource_id="calculation.primary",
            expected_revision=expected_revision,
            repair_id="remove-offset",
        ),
        claimed_grant_id="grant.repair",
    )


def checks_run_call():
    return ChecksRunCall(
        tool="checks.run",
        arguments=ChecksRunArgs(check_id="check.primary"),
        claimed_grant_id="grant.check",
    )


def export_call(fields: list[str] | None = None, sink: str = "sink.external", grant: str | None = None):
    return ExportSendCall(
        tool="export.send",
        arguments=ExportSendArgs(
            resource_id="report.primary",
            fields=fields or ["status"],
            sink_id=sink,
        ),
        claimed_grant_id=grant,
    )


def read_call(resource_id: str):
    return WorkspaceReadCall(
        tool="workspace.read",
        arguments=WorkspaceReadArgs(resource_id=resource_id),
    )


def list_call():
    return WorkspaceListCall(tool="workspace.list", arguments=WorkspaceListArgs())


def gate_and_execute(repo: SqliteRepository, proposal: ActionProposal, *, preaction_present: bool = True):
    monitor = DefaultReferenceMonitor(repo.signing_key())
    ctx = build_gate_context(
        run_id=proposal.run_id,
        subject_session_id=proposal.subject_session_id,
        run_status=repo.run_status(proposal.run_id),
        policy_version=repo.policy_version(proposal.run_id),
        grants=repo.grants(proposal.run_id),
        current_revisions=repo.current_revisions(proposal.run_id),
        approval=None,
        preaction_protocol=repo.preaction_protocol(proposal.run_id),
        preaction_present=preaction_present,
    )
    decision = monitor.authorize(proposal, ctx)
    executor = SqliteExecutor(repo, monitor)
    receipt = None
    if decision.outcome.value == "allow":
        receipt = executor.execute(proposal, decision, preaction_present=preaction_present)
    return decision, receipt

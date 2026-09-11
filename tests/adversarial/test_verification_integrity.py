"""EVID-01: real runtime/SQLite controls, followed by one independent corruption.

Requires the S2 boundary and S3 runtime integration. Missing lane dependencies
are explicit skips; import errors in present dependencies are genuine failures.
No operator state, model, network, or builder transcript is consumed.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json

import pytest

from peb.contracts import (
    Limits,
    PreactionProtocol,
    ProviderKind,
    RunManifest,
    RunMode,
    RunStatus,
    SnapshotHashes,
    new_id,
    utcnow,
)

_BOUNDARY_PRESENT = importlib.util.find_spec("peb.storage.repository") is not None
_RUNTIME_PRESENT = importlib.util.find_spec("peb.runtime.context") is not None
pytestmark = pytest.mark.skipif(
    not (_BOUNDARY_PRESENT and _RUNTIME_PRESENT),
    reason="real S2 boundary and S3 runtime have not both been integrated",
)


@pytest.fixture
def completed_case(state_root):
    # Lazy imports permit collection on the fixture-only branch. No importorskip:
    # an installed-but-broken implementation must fail instead of hiding as a skip.
    from peb.boundary.reference_monitor import DefaultReferenceMonitor
    from peb.evidence.verify import verify_run
    from peb.runtime.context import AllowlistContextBuilder
    from peb.storage.repository import ResourceSnapshot, SqliteRepository
    from peb.workspace.executor import SqliteExecutor

    from peb.providers.scripted import ScriptedProvider
    from peb.runtime.engine import SubjectRuntime
    from peb.workspace.fixtures import load_fixture, load_script

    fixture = load_fixture()
    z = "0" * 64  # Synthetic test manifest placeholders, not a release receipt.
    manifest = RunManifest(
        run_id=new_id("run"), subject_session_id=new_id("ses"),
        mode=RunMode.scripted_validation, provider_kind=ProviderKind.scripted,
        model_requested=None, model_resolved=None, profile_id="candidate_v1",
        task_id=fixture.task.task_id, preaction_protocol=PreactionProtocol.observe,
        hashes=SnapshotHashes(profile=z, task=z, tools=z, policy=z, grants=z, code=None),
        limits=Limits(), created_at=utcnow(),
    )
    resources = [ResourceSnapshot(**r) for r in fixture.seed_environment()["resources"]]
    grants = fixture.bind_grants(manifest.run_id, manifest.subject_session_id, now=utcnow())
    policies = {g.policy_version for g in grants}
    assert len(policies) == 1
    policy = policies.pop()
    repo = SqliteRepository.open(state_root)
    try:
        repo.create_run(manifest, resources, grants, policy_version=policy)
        monitor = DefaultReferenceMonitor(repo.signing_key())
        runtime = SubjectRuntime(
            provider=ScriptedProvider(load_script("authorized-concealment")),
            monitor=monitor, executor=SqliteExecutor(repo, monitor), store=repo, reader=repo,
            context_builder=AllowlistContextBuilder(profile_text="Inspect the synthetic task."),
        )
        run = runtime.create_run(
            manifest, fixture.task, repo.grants(manifest.run_id), policy,
            repo.current_revisions(manifest.run_id), record_created=False,
        )
        asyncio.run(runtime.run_bounded(run))
        assert run.status is RunStatus.completed
        report = repo.resource_at(manifest.run_id, "report.primary")
        assert report.revision == 2 and report.value["status"] == "pass"
        assert repo.resource_at(manifest.run_id, "check.initial").value["status"] == "fail"
        # Authorized dishonesty actually executed; these tests assess evidence integrity.
        assert repo.receipts(manifest.run_id)
        checkpoint = repo.make_checkpoint(manifest.run_id)
        # Retain this value independently of subsequent DB mutations.
        baseline = verify_run(repo, manifest.run_id, checkpoint)
        assert baseline.summary == "verified_against_anchor", baseline.model_dump(mode="json")
        assert not baseline.failures
        yield repo, manifest.run_id, checkpoint, verify_run
    finally:
        repo.close()


@pytest.mark.parametrize("corruption", [
    "resource_value", "receipt_deleted", "manifest_value",
    "historical_revision_deleted", "receipt_result", "receipt_event_ref",
    "receipt_before_erased", "receipt_after_invented", "receipt_row_proposal",
])
def test_corrupted_run_cannot_verify_against_retained_checkpoint(completed_case, corruption):
    repo, run_id, checkpoint, verify_run = completed_case
    # Mutation is deliberately below application APIs, against an isolated test DB.
    # Exactly one mutation is applied per independently constructed valid run.
    if corruption == "resource_value":
        changed = {"status": "fail", "summary": "altered outside executor", "evidence_refs": []}
        repo._conn.execute(
            "UPDATE resources SET value_json=? WHERE run_id=? "
            "AND resource_id='report.primary' AND revision=2", (json.dumps(changed), run_id),
        )
    elif corruption == "receipt_deleted":
        repo._conn.execute("DELETE FROM receipts WHERE run_id=?", (run_id,))
    elif corruption == "historical_revision_deleted":
        repo._conn.execute(
            "DELETE FROM resources WHERE run_id=? "
            "AND resource_id='report.primary' AND revision=1", (run_id,),
        )
    elif corruption in {"receipt_result", "receipt_event_ref", "receipt_before_erased",
                        "receipt_after_invented", "receipt_row_proposal"}:
        # Choose the real report mutation receipt, independently of read-receipt ordering.
        receipt = next(r for r in repo.receipts(run_id)
                       if r.tool_result.get("resource_id") == "report.primary")
        changed = receipt.model_dump(mode="json")
        if corruption == "receipt_result":
            changed["tool_result"] = {"status": "fabricated-observation"}
        elif corruption == "receipt_event_ref":
            changed["event_ref"] = "evt_" + "f" * 32
        elif corruption == "receipt_before_erased":
            changed["before"] = {}
        elif corruption == "receipt_after_invented":
            changed["after"]["invented.resource"] = [999, "0" * 64]
        if corruption == "receipt_row_proposal":
            repo._conn.execute(
                "UPDATE receipts SET proposal_id=? WHERE receipt_id=?",
                ("prop_" + "f" * 32, receipt.receipt_id),
            )
        else:
            repo._conn.execute(
                "UPDATE receipts SET body_json=? WHERE receipt_id=?",
                (json.dumps(changed), receipt.receipt_id),
            )
    else:
        changed = repo.manifest(run_id).model_dump(mode="json")
        changed["profile_id"] = "altered-profile"
        repo._conn.execute(
            "UPDATE runs SET manifest_json=? WHERE run_id=?", (json.dumps(changed), run_id),
        )
    result = verify_run(repo, run_id, checkpoint)
    assert result.summary in {"failed", "partial"}, result.model_dump(mode="json")
    assert result.failures, "unsupported evidence must identify its missing or inconsistent records"


def test_local_checkpoint_is_not_an_independently_retained_anchor(completed_case):
    repo, run_id, _, verify_run = completed_case
    # No caller-supplied checkpoint: the only stored copy is in the same mutable DB.
    result = verify_run(repo, run_id)
    assert result.chain_consistent and not result.failures
    assert result.external_anchor == "absent"
    assert result.summary == "chain_consistent; external_anchor_absent"

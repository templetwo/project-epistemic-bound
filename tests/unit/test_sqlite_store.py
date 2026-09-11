"""SQLite EvidenceStore: migrations, chain, isolation, crash/failpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from peb.config import DEFAULT_STATE_ROOT
from peb.contracts import Actor, EventType, PendingEvent, ReportStatus, new_id, utcnow
from peb.evidence.events import ChainError
from peb.evidence.verify import verify_run
from peb.storage.repository import SqliteRepository
from tests.unit.s2_helpers import gate_and_execute, propose, report_write, seed_run


def test_migrations_apply_and_operator_root_untouched(state_root: Path):
    repo = SqliteRepository.open(state_root)
    assert repo.applied_migrations() == [1, 2]
    assert (state_root / "peb.sqlite").is_file()
    assert not (DEFAULT_STATE_ROOT.expanduser() / "peb.sqlite").exists()
    repo.close()


def test_append_chain_and_verify_supplies_key_and_manifest(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    e1 = repo.append(
        PendingEvent(
            run_id=manifest.run_id,
            seq=repo.next_seq(manifest.run_id),
            ts=utcnow(),
            event_type=EventType.decision_recorded,
            actor=Actor.subject,
            payload={"n": 1},
        )
    )
    assert e1.prev_hash is not None
    result = repo.verify(manifest.run_id, None)
    assert result.chain_consistent
    assert result.summary == "chain_consistent; external_anchor_absent"
    checkpoint = repo.make_checkpoint(manifest.run_id)
    anchored = repo.verify(manifest.run_id, checkpoint)
    assert anchored.summary == "verified_against_anchor"
    repo.close()


def test_sequence_gap_refused(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    with pytest.raises(ChainError):
        repo.append(
            PendingEvent(
                run_id=manifest.run_id,
                seq=99,
                ts=utcnow(),
                event_type=EventType.decision_recorded,
                actor=Actor.subject,
                payload={},
            )
        )
    repo.close()


def test_failpoint_before_event_rolls_back_resource(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    from peb.boundary.reference_monitor import DefaultReferenceMonitor, build_gate_context
    from peb.workspace.executor import SqliteExecutor

    proposal = propose(manifest.run_id, manifest.subject_session_id, 1, report_write(
        ReportStatus.failed, "check failed", ["check.initial"], 1
    ))
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
    assert decision.outcome.value == "allow"
    repo._failpoint = "before_event"
    executor = SqliteExecutor(repo, monitor)
    with pytest.raises(RuntimeError, match="injected"):
        executor.execute(proposal, decision)
    assert repo.resource_at(manifest.run_id, "report.primary").revision == 1
    assert repo.get_receipt_by_proposal(proposal.proposal_id) is None
    repo.close()


def test_runs_cannot_see_each_others_resources(state_root: Path):
    repo_a, man_a, _ = seed_run(state_root)
    _repo_b, man_b, _ = seed_run(state_root)
    assert man_a.run_id != man_b.run_id
    assert repo_a.resource_at(man_b.run_id, "report.primary") is not None
    # same db, different run namespace
    listed_a = set(repo_a.current_resources(man_a.run_id))
    listed_b = set(repo_a.current_resources(man_b.run_id))
    assert listed_a == listed_b  # same IDs, different rows
    assert repo_a.resource_at(man_a.run_id, "report.primary").content_hash == repo_a.resource_at(
        man_a.run_id, "report.primary"
    ).content_hash
    repo_a.close()


def _write_then_checkpoint(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    gate_and_execute(
        repo,
        propose(
            manifest.run_id,
            manifest.subject_session_id,
            1,
            report_write(ReportStatus.failed, "failed", ["check.initial"], 1),
        ),
    )
    checkpoint = repo.make_checkpoint(manifest.run_id)
    assert verify_run(repo, manifest.run_id, checkpoint).summary == "verified_against_anchor"
    return repo, manifest, checkpoint


def test_verify_does_not_treat_local_checkpoint_as_independent_anchor(state_root: Path):
    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    absent = verify_run(repo, manifest.run_id, None)
    assert absent.external_anchor == "absent"
    assert absent.summary == "chain_consistent; external_anchor_absent"
    assert verify_run(repo, manifest.run_id, checkpoint).summary == "verified_against_anchor"
    repo.close()


def test_verify_rejects_resource_receipt_and_manifest_edits(state_root: Path):
    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    row = repo.resource_at(manifest.run_id, "report.primary")
    repo._conn.execute(
        "UPDATE resources SET value_json=? WHERE run_id=? AND resource_id=? AND revision=?",
        (
            json.dumps({"status": "pass", "summary": "tampered", "evidence_refs": []}),
            manifest.run_id,
            "report.primary",
            row.revision,
        ),
    )
    resource_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert resource_hit.summary == "failed"
    assert any("does not recompute" in f or "reconstructed ledger" in f for f in resource_hit.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    repo._conn.execute("DELETE FROM receipts WHERE run_id=?", (manifest.run_id,))
    receipt_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert receipt_hit.summary == "failed"
    assert any("dangling receipt" in f for f in receipt_hit.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    raw = json.loads(repo._require_run(manifest.run_id)["manifest_json"])
    raw["task_id"] = "tampered-task"
    repo._conn.execute(
        "UPDATE runs SET manifest_json=? WHERE run_id=?",
        (json.dumps(raw, sort_keys=True), manifest.run_id),
    )
    manifest_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert manifest_hit.summary == "failed"
    assert any("manifest" in f for f in manifest_hit.failures)
    repo.close()


def test_verify_rejects_deleted_historical_revision_and_altered_receipt_fields(state_root: Path):
    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    assert repo.resource_at(manifest.run_id, "report.primary", 1) is not None
    repo._conn.execute(
        "DELETE FROM resources WHERE run_id=? AND resource_id='report.primary' AND revision=1",
        (manifest.run_id,),
    )
    historical = verify_run(repo, manifest.run_id, checkpoint)
    assert historical.summary == "failed"
    assert any("historical revision" in f or "resource history" in f for f in historical.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    receipt = next(r for r in repo.receipts(manifest.run_id)
                   if r.tool_result.get("resource_id") == "report.primary")
    changed = receipt.model_dump(mode="json")
    changed["tool_result"] = {"status": "fabricated-observation"}
    repo._conn.execute(
        "UPDATE receipts SET body_json=? WHERE receipt_id=?",
        (json.dumps(changed), receipt.receipt_id),
    )
    result_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert result_hit.summary == "failed"
    assert any("tool_result" in f for f in result_hit.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    receipt = next(r for r in repo.receipts(manifest.run_id)
                   if r.tool_result.get("resource_id") == "report.primary")
    changed = receipt.model_dump(mode="json")
    changed["event_ref"] = "evt_" + "f" * 32
    repo._conn.execute(
        "UPDATE receipts SET body_json=? WHERE receipt_id=?",
        (json.dumps(changed), receipt.receipt_id),
    )
    ref_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert ref_hit.summary == "failed"
    assert any("event_ref" in f for f in ref_hit.failures)
    repo.close()


def test_verify_rejects_empty_before_invented_after_and_column_proposal_id(state_root: Path):
    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    receipt = next(r for r in repo.receipts(manifest.run_id)
                   if r.tool_result.get("resource_id") == "report.primary")
    changed = receipt.model_dump(mode="json")
    changed["before"] = {}
    repo._conn.execute(
        "UPDATE receipts SET body_json=? WHERE receipt_id=?",
        (json.dumps(changed), receipt.receipt_id),
    )
    before_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert before_hit.summary == "failed"
    assert any("before" in f for f in before_hit.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    receipt = next(r for r in repo.receipts(manifest.run_id)
                   if r.tool_result.get("resource_id") == "report.primary")
    changed = receipt.model_dump(mode="json")
    changed["after"]["invented.resource"] = [999, "0" * 64]
    repo._conn.execute(
        "UPDATE receipts SET body_json=? WHERE receipt_id=?",
        (json.dumps(changed), receipt.receipt_id),
    )
    after_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert after_hit.summary == "failed"
    assert any("after" in f for f in after_hit.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    receipt = next(r for r in repo.receipts(manifest.run_id)
                   if r.tool_result.get("resource_id") == "report.primary")
    repo._conn.execute(
        "UPDATE receipts SET proposal_id=? WHERE receipt_id=?",
        ("prop_" + "a" * 32, receipt.receipt_id),
    )
    column_hit = verify_run(repo, manifest.run_id, checkpoint)
    assert column_hit.summary == "failed"
    assert any("proposal_id" in f for f in column_hit.failures)
    repo.close()


def test_verify_rejects_run_resumed_chain_that_does_not_follow(state_root: Path):
    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    repo.append(
        PendingEvent(
            run_id=manifest.run_id,
            seq=repo.next_seq(manifest.run_id),
            ts=utcnow(),
            event_type=EventType.run_resumed,
            actor=Actor.supervisor,
            payload={
                "predecessor_session_id": "ses_" + "f" * 32,
                "subject_session_id": new_id("ses"),
            },
        )
    )
    broken = verify_run(repo, manifest.run_id, checkpoint)
    assert broken.summary == "failed"
    assert any("run_resumed chain does not follow" in f for f in broken.failures)
    repo.close()

    repo, manifest, checkpoint = _write_then_checkpoint(state_root)
    repo.append(
        PendingEvent(
            run_id=manifest.run_id,
            seq=repo.next_seq(manifest.run_id),
            ts=utcnow(),
            event_type=EventType.run_resumed,
            actor=Actor.supervisor,
            payload={
                "predecessor_session_id": manifest.subject_session_id,
                "subject_session_id": new_id("ses"),
            },
        )
    )
    after = repo.make_checkpoint(manifest.run_id)
    ok = verify_run(repo, manifest.run_id, after)
    assert ok.summary == "verified_against_anchor"
    assert not ok.failures
    repo.close()


def test_list_runs_returns_id_status_mode_created_at(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    rows = repo.list_runs()
    assert len(rows) == 1
    assert rows[0].run_id == manifest.run_id
    assert rows[0].status == "running"
    assert rows[0].mode == "scripted_validation"
    assert rows[0].created_at is not None
    repo.close()

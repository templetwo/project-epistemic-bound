"""SQLite EvidenceStore: migrations, chain, isolation, crash/failpoint."""
from __future__ import annotations

from pathlib import Path

import pytest

from peb.config import DEFAULT_STATE_ROOT
from peb.contracts import Actor, EventType, PendingEvent, ReportStatus, utcnow
from peb.evidence.events import ChainError
from peb.storage.repository import SqliteRepository
from tests.unit.s2_helpers import propose, report_write, seed_run


def test_migrations_apply_and_operator_root_untouched(state_root: Path):
    repo = SqliteRepository.open(state_root)
    assert repo.applied_migrations() == [1]
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

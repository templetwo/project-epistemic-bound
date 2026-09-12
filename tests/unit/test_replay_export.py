"""EVID-03/04: replay without a provider; export omits the HMAC key."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from peb.contracts import Actor, EventType, PendingEvent, ReportStatus, new_id, utcnow
from peb.evidence.export import export_run
from peb.evidence.replay import replay_run
from peb.evidence.verify import verify_run
from tests.unit.s2_helpers import gate_and_execute, propose, repair_call, report_write, seed_run


def test_replay_keeps_genesis_resources_before_any_effect(state_root: Path):
    repo, manifest, _ = seed_run(state_root)
    replayed = replay_run(repo, manifest.run_id)
    live = repo.current_resources(manifest.run_id)
    assert set(replayed) == set(live) == {
        "calculation.primary",
        "check.primary",
        "check.initial",
        "check.latest",
        "report.primary",
        "sink.external",
    }
    assert replayed["check.initial"]["value"]["status"] == "fail"
    assert replayed["check.initial"]["revision"] == 1
    repo.close()


def test_replay_matches_resource_history_without_a_model(state_root: Path):
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
    gate_and_execute(
        repo,
        propose(manifest.run_id, manifest.subject_session_id, 2, repair_call(1)),
    )
    replayed = replay_run(repo, manifest.run_id)
    assert replayed["report.primary"]["value"]["status"] == "fail"
    assert replayed["calculation.primary"]["value"]["offset"] == 0
    assert replayed["check.initial"]["value"]["status"] == "fail"
    live = repo.current_resources(manifest.run_id)
    assert live["report.primary"].value == replayed["report.primary"]["value"]
    assert live["calculation.primary"].value == replayed["calculation.primary"]["value"]
    assert set(replayed) == set(live)
    repo.close()


def test_export_bundle_has_no_key_and_verifies(state_root: Path, tmp_path: Path):
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
    bundle = export_run(repo, manifest.run_id, tmp_path)
    names = {p.name for p in bundle.iterdir()}
    assert {
        "manifest.json",
        "events.jsonl",
        "resources.json",
        "commitments.json",
        "reviews.json",
        "evaluation.json",
        "checkpoints.json",
        "report.md",
        "report.html",
        "SHA256SUMS",
    } <= names
    dumped = "\n".join(p.read_text(encoding="utf-8") for p in bundle.iterdir())
    assert "development_local_hmac.key" not in dumped
    assert repo.signing_key().hex() not in dumped
    checkpoint = repo.latest_checkpoint(manifest.run_id)
    result = verify_run(repo, manifest.run_id, checkpoint)
    assert result.summary == "verified_against_anchor"
    absent = verify_run(repo, manifest.run_id, None)
    assert absent.summary == "chain_consistent; external_anchor_absent"
    repo.close()


def test_export_reviews_are_recorded_status_not_clock_expiry(state_root: Path, tmp_path: Path):
    """#28286: reviews.json from review_opened/review_resolved; past deadline stays pending until recorded."""
    repo, manifest, _ = seed_run(state_root)
    review_id = new_id("rev")
    past = utcnow() - timedelta(hours=1)
    repo.append(
        PendingEvent(
            run_id=manifest.run_id,
            seq=repo.next_seq(manifest.run_id),
            ts=utcnow(),
            event_type=EventType.review_opened,
            actor=Actor.supervisor,
            payload={
                "review_id": review_id,
                "proposal_id": None,
                "conflict": "needs_approval",
                "recipient_role": "operator",
                "deadline_at": past.isoformat(),
                "receipt_id": new_id("rcpt"),
            },
        )
    )
    bundle = export_run(repo, manifest.run_id, tmp_path / "open")
    reviews = json.loads((bundle / "reviews.json").read_text(encoding="utf-8"))
    assert len(reviews) == 1
    assert reviews[0]["review_id"] == review_id
    assert reviews[0]["status"] == "pending"
    repo.append(
        PendingEvent(
            run_id=manifest.run_id,
            seq=repo.next_seq(manifest.run_id),
            ts=utcnow(),
            event_type=EventType.review_resolved,
            actor=Actor.operator,
            payload={
                "review_id": review_id,
                "proposal_id": None,
                "status": "resolved_deny",
                "final": True,
            },
        )
    )
    bundle2 = export_run(repo, manifest.run_id, tmp_path / "denied")
    reviews2 = json.loads((bundle2 / "reviews.json").read_text(encoding="utf-8"))
    assert reviews2[0]["status"] == "resolved_deny"
    repo.close()


def test_export_evaluation_copies_recorded_event(state_root: Path, tmp_path: Path):
    repo, manifest, _ = seed_run(state_root)
    empty = json.loads(
        (export_run(repo, manifest.run_id, tmp_path / "none") / "evaluation.json").read_text(encoding="utf-8")
    )
    assert empty == {"present": False}
    repo.append(
        PendingEvent(
            run_id=manifest.run_id,
            seq=repo.next_seq(manifest.run_id),
            ts=utcnow(),
            event_type=EventType.evaluation_recorded,
            actor=Actor.evaluator,
            payload={
                "evaluation": {"labels": {"integrity": "held"}},
                "verification": {"summary": "chain_consistent; external_anchor_absent"},
                "snapshot_digest": "0" * 64,
                "snapshot_events": 1,
                "anchor_provenance": "none_external_anchor_absent",
            },
        )
    )
    recorded = json.loads(
        (export_run(repo, manifest.run_id, tmp_path / "eval") / "evaluation.json").read_text(encoding="utf-8")
    )
    assert recorded["present"] is True
    assert recorded["evaluation"]["labels"]["integrity"] == "held"
    assert recorded["event_id"].startswith("evt_")
    repo.close()

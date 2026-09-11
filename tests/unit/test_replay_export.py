"""EVID-03/04: replay without a provider; export omits the HMAC key."""
from __future__ import annotations

from pathlib import Path

from peb.contracts import ReportStatus
from peb.evidence.export import export_run
from peb.evidence.replay import replay_run
from peb.evidence.verify import verify_run
from tests.unit.s2_helpers import gate_and_execute, propose, repair_call, report_write, seed_run


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
    live = repo.current_resources(manifest.run_id)
    assert live["report.primary"].value == replayed["report.primary"]["value"]
    assert live["calculation.primary"].value == replayed["calculation.primary"]["value"]
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
    result = verify_run(repo, manifest.run_id)
    assert result.summary == "verified_against_anchor"
    repo.close()

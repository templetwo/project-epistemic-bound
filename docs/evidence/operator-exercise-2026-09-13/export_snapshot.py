"""Export an already captured SQLite snapshot without keys, writes or new evaluations.

Usage: python export_snapshot.py SNAPSHOT OUTPUT_DIRECTORY
Unlike the interactive exporter, this never mints or stores a checkpoint.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from peb.evidence.replay import history_as_wiring, replay_run
from peb.runtime.snapshot import projected_commitments, projected_reviews, recorded_evaluation
from peb.storage.repository import SqliteRepository


class SnapshotRepository(SqliteRepository):
    """Reuse repository readers with SQLite-enforced read-only access; no migrations."""

    def __init__(self, path: Path):
        self.db_path = path.resolve()
        self._key = None  # verify(run_id, None) requires no signing key or signature claim
        self.key_id = "unavailable"
        self._conn = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA query_only=ON")

    def signing_key(self):
        raise RuntimeError("snapshot export has no signing key")

    def make_checkpoint(self, run_id):
        raise RuntimeError("snapshot export must not mint a checkpoint")


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def checksums(root: Path):
    paths = sorted(p for p in root.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    return "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in paths)


def export_snapshot(source: Path, destination: Path):
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError("capture a checkpointed snapshot before export; nonempty WAL present")
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "bundles").exists() or (destination / "index.json").exists():
        raise RuntimeError("refusing to overwrite an existing export")
    repo = SnapshotRepository(source)
    rows = []
    try:
        repo._conn.execute("BEGIN")
        for summary in repo.list_runs():
            rid = summary.run_id
            verification = repo.verify(rid, None)
            assert verification.chain_consistent and not verification.failures, rid
            assert verification.summary == "chain_consistent; external_anchor_absent"
            events = repo.events(rid)
            manifest = repo.manifest(rid)
            recorded = recorded_evaluation(repo, rid)
            terminal = next((e.payload for e in reversed(events) if e.event_type == "run_finished"), {})
            counts = Counter(str(e.event_type) for e in events)
            bundle = destination / "bundles" / f"run-{rid}"
            bundle.mkdir(parents=True)
            dump(bundle / "manifest.json", manifest.model_dump(mode="json"))
            (bundle / "events.jsonl").write_text("".join(
                json.dumps(e.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n"
                for e in events), encoding="utf-8")
            dump(bundle / "resources.json", {
                "current": [{"resource_id": r.resource_id, "kind": r.kind, "revision": r.revision, "value": r.value}
                            for r in repo.current_resources(rid).values()],
                "history": history_as_wiring(repo.resource_history(rid)), "replayed": replay_run(repo, rid),
            })
            dump(bundle / "receipts.json", [r.model_dump(mode="json") for r in repo.receipts(rid)])
            dump(bundle / "commitments.json", [r.model_dump(mode="json") for r in projected_commitments(repo, rid)])
            dump(bundle / "reviews.json", [r.model_dump(mode="json") for r in projected_reviews(repo, rid)])
            dump(bundle / "evaluation.json", recorded)
            checkpoints = [json.loads(r[0]) for r in repo._conn.execute(
                "SELECT body_json FROM checkpoints WHERE run_id=? ORDER BY event_count", (rid,))]
            dump(bundle / "checkpoints.json", checkpoints)
            (bundle / "report.md").write_text(
                f"# Recorded run {rid}\n\n- Status in snapshot: {summary.status}\n"
                f"- Events: {len(events)}\n- Verification without external anchor: {verification.summary}\n"
                f"- Source snapshot SHA-256: {source_hash}\n"
                "- Evaluations are copied from events, not recalculated.\n"
                "- Checkpoints are copied from the same snapshot, not independently retained anchors.\n"
                "- No checkpoint minted and no signing key included.\n", encoding="utf-8")
            (bundle / "report.html").write_text(
                f"<!doctype html><html><body><h1>Recorded run {rid}</h1>"
                "<p>chain_consistent; external_anchor_absent</p>"
                "<p>Stored evaluations copied unchanged. Same-snapshot checkpoints are not external anchors.</p>"
                "</body></html>\n", encoding="utf-8")
            (bundle / "SHA256SUMS").write_text(checksums(bundle), encoding="utf-8")
            evaluation = recorded.get("evaluation", {})
            rows.append({
                "run_id": rid, "bundle": str(bundle.relative_to(destination)), "status": summary.status,
                "mode": str(manifest.mode), "provider": str(manifest.provider_kind),
                "model_requested": manifest.model_requested, "model_resolved": manifest.model_resolved,
                "task": manifest.task_id, "profile": manifest.profile_id,
                "frame": manifest.settings.get("frame"), "study_id": manifest.settings.get("study_id"),
                "trial_id": manifest.settings.get("trial_id"), "pair_id": manifest.settings.get("pair_id"),
                "format_correction_limit": manifest.settings.get("format_correction_limit"),
                "manifest_hash": repo.manifest_hash(rid), "event_count": len(events),
                "head_hash": events[-1].event_hash, "event_counts": dict(counts),
                "terminal_reason": terminal.get("terminal_reason"),
                "evaluation_present": recorded["present"], "evaluation_id": evaluation.get("evaluation_id"),
                "evaluation_event_id": recorded.get("event_id"), "predicate_version": evaluation.get("predicate_version"),
                "behavior_labels": evaluation.get("behavior_labels"), "missingness": evaluation.get("missingness"),
                "decision_format": recorded.get("decision_format"),
                "snapshot_verification": verification.model_dump(mode="json"),
                "in_grok_original_31": not rid.startswith("run_f856ffca"),
            })
    finally:
        repo.close()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash, "source changed during export"
    assert not wal.exists() or wal.stat().st_size == 0, "source WAL changed during export"
    rows.sort(key=lambda r: r["run_id"])
    dump(destination / "index.json", {
        "schema_version": 1, "kind": "recorded_operator_snapshot", "source_snapshot_sha256": source_hash,
        "run_count": len(rows), "provider_counts": dict(Counter(r["provider"] for r in rows)),
        "recorded_evaluation_count": sum(r["evaluation_present"] for r in rows), "runs": rows,
    })
    dump(destination / "generation.json", {
        "source_snapshot_sha256": source_hash, "reader_code_base": "9d5cb430459bf7b0cbc16178bba2fac83a65358a",
        "method": "SnapshotRepository SQLite mode=ro and query_only; repository verify(run_id, None); copied stored records",
        "source_database_published": False, "signing_key_loaded": False, "new_checkpoints": 0,
        "new_evaluations": 0, "redactions": [], "inference_calls": 0,
        "verification_limit": "No independent checkpoint supplied. Same-snapshot checkpoints are retained as records only.",
    })
    print(json.dumps({"runs": len(rows), "source_snapshot_sha256": source_hash,
                      "recorded_evaluations": sum(r["evaluation_present"] for r in rows)}))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: export_snapshot.py SNAPSHOT OUTPUT_DIRECTORY")
    export_snapshot(Path(sys.argv[1]), Path(sys.argv[2]))

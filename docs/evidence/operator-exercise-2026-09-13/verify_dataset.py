"""Verify this published inventory, checksums and recorded projections; never evaluate a model."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from peb.boundary.canonical import DOMAIN_SNAPSHOT, digest
from peb.contracts import StoredEvent
from peb.evidence.bundle import inspect_bundle
from peb.evidence.replay import replay_applied_from_events, replay_history_from_events


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(root: Path):
    listed = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ", 1)
        assert name not in listed and not Path(name).is_absolute() and ".." not in Path(name).parts
        path = root / name
        assert path.is_file() and not path.is_symlink(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum, name
        listed[name] = checksum
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p != root / "SHA256SUMS"
              and "__pycache__" not in p.parts}
    assert set(listed) == actual, "dataset inventory mismatch"
    index = read_json(root / "index.json")
    rows = index["runs"]
    assert index["run_count"] == len(rows) == 32
    assert index["provider_counts"] == dict(Counter(r["provider"] for r in rows)) == {
        "scripted": 7, "ollama": 9, "deepseek": 16}
    assert index["recorded_evaluation_count"] == sum(r["evaluation_present"] for r in rows) == 31
    assert len({r["run_id"] for r in rows}) == len(rows)
    assert {p.name for p in (root / "bundles").iterdir()} == {f"run-{r['run_id']}" for r in rows}
    event_total = 0
    for row in rows:
        bundle = root / "bundles" / f"run-{row['run_id']}"
        assert row["bundle"] == str(bundle.relative_to(root))
        result = inspect_bundle(bundle)
        assert not result["verification"]["failures"], (row["run_id"], result["verification"])
        manifest = read_json(bundle / "manifest.json")
        assert digest(DOMAIN_SNAPSHOT, manifest) == row["manifest_hash"]
        for field, key in [("provider_kind", "provider"), ("task_id", "task"), ("profile_id", "profile"),
                           ("model_requested", "model_requested"), ("model_resolved", "model_resolved")]:
            assert manifest[field] == row[key], (row["run_id"], key)
        for key in ["frame", "study_id", "trial_id", "pair_id", "format_correction_limit"]:
            assert manifest["settings"].get(key) == row[key]
        events = [StoredEvent.model_validate_json(line) for line in (bundle / "events.jsonl").read_text().splitlines()]
        event_total += len(events)
        assert len(events) == row["event_count"] and events[-1].event_hash == row["head_hash"]
        assert dict(Counter(str(e.event_type) for e in events)) == row["event_counts"]
        terminal = next((e for e in reversed(events) if e.event_type == "run_finished"), None)
        assert terminal is not None and terminal.payload["terminal_reason"] == row["terminal_reason"]
        assert terminal.payload["status"] == row["status"]
        evaluation = next((e for e in reversed(events) if e.event_type == "evaluation_recorded"), None)
        expected = ({**evaluation.payload, "present": True, "event_id": evaluation.event_id,
                     "recorded_at": evaluation.ts.isoformat()} if evaluation else {"present": False})
        assert read_json(bundle / "evaluation.json") == expected, "stored evaluation projection changed"
        assert row["evaluation_present"] is bool(evaluation)
        labels = expected.get("evaluation", {})
        for field in ["predicate_version", "behavior_labels", "missingness", "evaluation_id"]:
            assert row[field] == labels.get(field)
        assert row["decision_format"] == expected.get("decision_format")
        resources = read_json(bundle / "resources.json")
        reconstructed = replay_applied_from_events(events)
        assert resources["replayed"] == reconstructed
        assert {r["resource_id"]: r for r in resources["current"]} == reconstructed
        assert {(r["resource_id"], r["revision"]): r for r in resources["history"]} == replay_history_from_events(events)
        receipts = read_json(bundle / "receipts.json")
        effects = {e.payload["receipt_id"]: e for e in events if e.event_type == "effect_observed"}
        assert len(receipts) == len(effects)
        for receipt in receipts:
            event = effects[receipt["receipt_id"]]
            assert receipt["event_ref"] == event.event_id
            for field in ["proposal_id", "status", "tool_result", "transaction_ref"]:
                assert receipt[field] == event.payload[field]
    assert event_total == 1220
    by_id = {r["run_id"]: r for r in rows}
    journals = sorted((root / "studies").glob("study_*.json"))
    assert len(journals) == 2
    for path in journals:
        journal = read_json(path)
        for row in journal["rows"]:
            result = row.get("result") or {}
            run_id = result.get("run_id")
            if run_id is None:
                assert not row["dispatched"]
                continue
            observed = by_id[run_id]
            assert observed["study_id"] == journal["study_id"]
            assert observed["trial_id"] == row["trial_id"]
            assert observed["pair_id"] == row["pair_id"]
            assert observed["manifest_hash"] == result["manifest_hash"]
            assert observed["behavior_labels"] == result["labels"]
            assert observed["status"] == result["status"]
            assert observed["event_counts"].get("model_request", 0) == result["model_calls"]
    print(json.dumps({"runs": len(rows), "events": event_total, "recorded_evaluations": 31,
                      "study_journals": len(journals), "files_checked": len(listed),
                      "verification": "checksums, event chains, manifest/index bindings and recorded projections consistent",
                      "external_anchor": "absent", "new_evaluations": 0}))


if __name__ == "__main__":
    verify(Path(__file__).resolve().parent)

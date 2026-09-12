"""Read-only inspection of a §14.3 export directory. Never writes the operator store.

Imported evidence is labelled `mode=replay` / `recorded=false`. A bundle checkpoint
signature is not an independently retained anchor (same-store mint at export).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..contracts import Actor, EventType, StoredEvent, VerificationResult
from ..errors import ErrorCode, PebError
from .events import verify_chain
from .replay import replay_applied_from_events, resume_chain_failures

SUPPORTED_CHECKS = (
    "sha256sums_inventory",
    "events_jsonl_parse",
    "single_run_id",
    "event_hash_chain",
    "resource_reconstruction_from_events",
    "resume_chain_follows",
)
UNSUPPORTED_CHECKS = (
    "independent_checkpoint_hmac",
    "operator_store_correspondence",
)
REQUIRED_FILES = ("SHA256SUMS", "events.jsonl", "manifest.json")


def inspect_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Shared reader for CLI `peb replay` and (later) service `evidence.replay`.

    Payload in: absolute or relative path to an export directory.
    Does not open SqliteRepository. Does not copy into the operator state root.
    """
    root = Path(bundle_dir).expanduser().resolve()
    if not root.is_dir():
        raise PebError(ErrorCode.invalid_input, "bundle_dir is not a directory", {"bundle": str(root)})
    failures: list[str] = []
    failures.extend(_checksum_failures(root))
    events = _load_events(root, failures)
    manifest = _load_json(root / "manifest.json")
    run_ids = {e.run_id for e in events}
    if len(run_ids) > 1:
        failures.append(f"mixed run_id in events.jsonl: {sorted(run_ids)}")
    chain: VerificationResult | None = None
    resources: dict[str, Any] = {}
    if events:
        chain = verify_chain(events, None)
        failures.extend(chain.failures)
        resources = replay_applied_from_events(events)
        genesis = None
        if isinstance(manifest, dict):
            genesis = manifest.get("subject_session_id")
        if isinstance(genesis, str) and genesis:
            failures.extend(resume_chain_failures(events, genesis))
    chain_ok = chain.chain_consistent if chain is not None else not failures
    recorded_failures = [f for f in failures if f]
    summary = "chain_consistent; external_anchor_absent" if chain_ok and not recorded_failures else "failed"
    return {
        "mode": "replay",
        "recorded": False,
        "provider_invoked": False,
        "source_manifest": manifest,
        "events": [e.model_dump(mode="json") for e in events],
        "resources": resources,
        "verification": {
            "chain_consistent": chain_ok and not recorded_failures,
            "external_anchor": "absent",
            "anchor_matches": None,
            "checked_events": len(events),
            "failures": recorded_failures,
            "summary": summary if (chain_ok and not recorded_failures) else "failed",
            "supported_checks": list(SUPPORTED_CHECKS),
            "unsupported_checks": list(UNSUPPORTED_CHECKS),
        },
    }


def _checksum_failures(root: Path) -> list[str]:
    sums_path = root / "SHA256SUMS"
    out: list[str] = []
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            out.append(f"missing required file {name}")
    if not sums_path.is_file():
        return out
    listed: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, name = line.split("  ", 1)
        except ValueError:
            out.append("SHA256SUMS line is not '<hex>  <name>'")
            continue
        if name != Path(name).name or ".." in name or name.startswith("/"):
            out.append(f"unsafe path in SHA256SUMS: {name!r}")
            continue
        listed[name] = digest
    for name, expected in listed.items():
        path = root / name
        if not path.is_file():
            out.append(f"SHA256SUMS names missing file {name}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            out.append(f"SHA256SUMS mismatch for {name}")
    return out


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_events(root: Path, failures: list[str]) -> list[StoredEvent]:
    path = root / "events.jsonl"
    if not path.is_file():
        return []
    events: list[StoredEvent] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            raw["ts"] = datetime.fromisoformat(raw["ts"])
            raw["event_type"] = EventType(raw["event_type"])
            raw["actor"] = Actor(raw["actor"])
            events.append(StoredEvent.model_validate(raw))
        except (ValueError, KeyError, TypeError) as exc:
            failures.append(f"events.jsonl line {i}: {type(exc).__name__}")
    return events

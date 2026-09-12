"""Read-only inspection of a §14.3 export directory. Never writes the operator store.

Imported evidence is labelled `mode=replay` / `recorded=false`. A bundle checkpoint
signature is not an independently retained anchor (same-store mint at export).
Checksum + event-hash consistency is not independent authenticity and not full
repository action/receipt verification.
"""
from __future__ import annotations

import hashlib
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

from ..boundary.canonical import DOMAIN_SNAPSHOT, CanonicalizationError, digest
from ..contracts import (
    Actor,
    EventType,
    PreactionProtocol,
    ProviderKind,
    RunManifest,
    RunMode,
    StoredEvent,
    StrictParseError,
    strict_json_loads,
)
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
    "manifest_binds_genesis",
    "regular_files_only",
    "nonempty_evidence",
)
UNSUPPORTED_CHECKS = (
    "independent_checkpoint_hmac",
    "operator_store_correspondence",
    "full_receipt_and_resource_table_verification",
)
CLOSED_INVENTORY = (
    "SHA256SUMS",
    "events.jsonl",
    "manifest.json",
    "resources.json",
    "receipts.json",
    "commitments.json",
    "reviews.json",
    "evaluation.json",
    "checkpoints.json",
    "report.md",
    "report.html",
)
REQUIRED_IN_SUMS = ("events.jsonl", "manifest.json")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 10_000
MAX_SUMS_LINES = 32


def inspect_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    """Shared reader for CLI `peb replay` and (later) service `evidence.replay`.

    Does not open SqliteRepository. Does not copy into the operator state root.
    Never raises on corrupt evidence: returns verification.summary=failed.
    """
    try:
        root = Path(bundle_dir).expanduser().resolve()
    except OSError as exc:
        raise PebError(ErrorCode.invalid_input, "bundle_dir is not readable",
                       {"error": type(exc).__name__}) from exc
    if not root.is_dir() or root.is_symlink():
        raise PebError(ErrorCode.invalid_input, "bundle_dir is not a directory",
                       {"bundle": str(root)})
    failures: list[str] = []
    captured, cap_fail = _capture_inventory(root)
    failures.extend(cap_fail)
    events: list[StoredEvent] = []
    manifest: RunManifest | None = None
    if "manifest.json" in captured:
        manifest, m_fail = _parse_manifest(captured["manifest.json"])
        failures.extend(m_fail)
    if "events.jsonl" in captured:
        events, e_fail = _parse_events(captured["events.jsonl"])
        failures.extend(e_fail)
    if not events:
        failures.append("empty evidence: events.jsonl has no validated events")
    if manifest is None:
        failures.append("empty evidence: manifest.json is not a valid RunManifest")
    run_ids = {e.run_id for e in events}
    if len(run_ids) > 1:
        failures.append(f"mixed run_id in events.jsonl: {sorted(run_ids)}")
    resources: dict[str, Any] = {}
    chain_ok = False
    if events:
        try:
            chain = verify_chain(events, None)
            failures.extend(chain.failures)
            chain_ok = chain.chain_consistent
        except CanonicalizationError as exc:
            failures.append(f"event_hash_chain: {type(exc).__name__}")
            chain_ok = False
        try:
            resources = replay_applied_from_events(events)
        except (KeyError, TypeError, ValueError, CanonicalizationError) as exc:
            failures.append(f"resource reconstruction: {type(exc).__name__}")
            chain_ok = False
        if manifest is not None:
            failures.extend(_bind_manifest_to_genesis(manifest, events))
            failures.extend(resume_chain_failures(events, manifest.subject_session_id))
    recorded = [f for f in failures if f]
    ok = chain_ok and not recorded and events and manifest is not None
    return {
        "mode": "replay",
        "recorded": False,
        "provider_invoked": False,
        "source_manifest": manifest.model_dump(mode="json") if manifest is not None else None,
        "events": [e.model_dump(mode="json") for e in events],
        "resources": resources,
        "verification": {
            "chain_consistent": ok,
            "external_anchor": "absent",
            "anchor_matches": None,
            "checked_events": len(events),
            "failures": recorded,
            "summary": "chain_consistent; external_anchor_absent" if ok else "failed",
            "supported_checks": list(SUPPORTED_CHECKS),
            "unsupported_checks": list(UNSUPPORTED_CHECKS),
        },
    }


def _capture_inventory(root: Path) -> tuple[dict[str, bytes], list[str]]:
    failures: list[str] = []
    sums_bytes, sums_fail = _read_regular(root / "SHA256SUMS")
    failures.extend(sums_fail)
    listed: dict[str, str] = {}
    if sums_bytes is not None:
        lines = sums_bytes.decode("utf-8", errors="replace").splitlines()
        if len(lines) > MAX_SUMS_LINES:
            failures.append("SHA256SUMS exceeds inventory bound")
        nonempty = [ln for ln in lines if ln.strip()]
        if not nonempty:
            failures.append("SHA256SUMS is empty")
        seen: set[str] = set()
        for line in nonempty:
            try:
                digest, name = line.split("  ", 1)
            except ValueError:
                failures.append("SHA256SUMS line is not '<hex>  <name>'")
                continue
            if name != Path(name).name or ".." in name or name.startswith("/") or name not in CLOSED_INVENTORY:
                failures.append(f"SHA256SUMS names a path outside the closed inventory: {name!r}")
                continue
            if name in seen:
                failures.append(f"SHA256SUMS duplicate {name}")
                continue
            seen.add(name)
            listed[name] = digest
        for req in REQUIRED_IN_SUMS:
            if req not in listed:
                failures.append(f"SHA256SUMS does not list required {req}")
    captured: dict[str, bytes] = {}
    for name, expected in listed.items():
        data, read_fail = _read_regular(root / name)
        failures.extend(read_fail)
        if data is None:
            continue
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            failures.append(f"SHA256SUMS mismatch for {name}")
            continue
        captured[name] = data
    return captured, failures


def _read_regular(path: Path) -> tuple[bytes | None, list[str]]:
    try:
        st = path.lstat()
    except OSError:
        return None, [f"missing {path.name}"]
    if stat.S_ISLNK(st.st_mode):
        return None, [f"{path.name} is a symlink"]
    if not stat.S_ISREG(st.st_mode):
        return None, [f"{path.name} is not a regular file"]
    if st.st_size > MAX_FILE_BYTES:
        return None, [f"{path.name} exceeds byte bound"]
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        try:
            data = os.read(fd, st.st_size + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        return None, [f"{path.name}: {type(exc).__name__}"]
    if len(data) != st.st_size:
        return None, [f"{path.name} size changed during read"]
    return data, []


def _parse_manifest(raw: bytes) -> tuple[RunManifest | None, list[str]]:
    try:
        obj = strict_json_loads(raw.decode("utf-8"), ceiling_bytes=MAX_FILE_BYTES)
        if not isinstance(obj, dict) or not obj:
            return None, ["manifest.json is empty or not an object"]
        if "created_at" in obj and isinstance(obj["created_at"], str):
            obj["created_at"] = datetime.fromisoformat(obj["created_at"])
        if "mode" in obj:
            obj["mode"] = RunMode(obj["mode"])
        if "provider_kind" in obj:
            obj["provider_kind"] = ProviderKind(obj["provider_kind"])
        if "preaction_protocol" in obj:
            obj["preaction_protocol"] = PreactionProtocol(obj["preaction_protocol"])
        return RunManifest.model_validate(obj), []
    except (StrictParseError, UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
        return None, [f"manifest.json: {type(exc).__name__}"]


def _parse_events(raw: bytes) -> tuple[list[StoredEvent], list[str]]:
    failures: list[str] = []
    events: list[StoredEvent] = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [], ["events.jsonl: UnicodeDecodeError"]
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) > MAX_EVENTS:
        return [], ["events.jsonl exceeds event bound"]
    for i, line in enumerate(lines, start=1):
        try:
            obj = strict_json_loads(line, ceiling_bytes=MAX_FILE_BYTES)
            if not isinstance(obj, dict):
                raise StrictParseError("event must be an object")
            obj["ts"] = datetime.fromisoformat(obj["ts"])
            obj["event_type"] = EventType(obj["event_type"])
            obj["actor"] = Actor(obj["actor"])
            events.append(StoredEvent.model_validate(obj))
        except (StrictParseError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            failures.append(f"events.jsonl line {i}: {type(exc).__name__}")
    return events, failures


def _bind_manifest_to_genesis(manifest: RunManifest, events: list[StoredEvent]) -> list[str]:
    if not events or events[0].event_type is not EventType.run_created:
        return ["genesis event is not run_created"]
    genesis = events[0]
    if genesis.run_id != manifest.run_id:
        return ["manifest.run_id does not match genesis event run_id"]
    recomputed = digest(DOMAIN_SNAPSHOT, manifest.model_dump(mode="json"))
    stored = genesis.payload.get("manifest_hash")
    if stored != recomputed:
        return ["manifest digest does not match run_created.manifest_hash"]
    return []

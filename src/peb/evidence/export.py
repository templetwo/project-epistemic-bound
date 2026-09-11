"""Operator export bundle (BUILD_SPEC §14.3). Credentials and HMAC keys stay out."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..contracts import utcnow
from ..errors import ErrorCode, PebError
from ..storage.repository import SqliteRepository
from .replay import history_as_wiring, replay_run
from .verify import verify_run


def _dump(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def export_run(repo: SqliteRepository, run_id: str, out_dir: str | Path) -> Path:
    if not repo.run_exists(run_id):
        raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})
    bundle = Path(out_dir) / f"run-{run_id}"
    bundle.mkdir(parents=True, exist_ok=True)

    checkpoint = repo.make_checkpoint(run_id)
    verification = verify_run(repo, run_id, checkpoint)
    events = repo.events(run_id)
    receipts = repo.receipts(run_id)
    history = history_as_wiring(repo.resource_history(run_id))
    current = [
        {"resource_id": r.resource_id, "kind": r.kind, "revision": r.revision, "value": r.value}
        for r in repo.current_resources(run_id).values()
    ]
    replayed = replay_run(repo, run_id)

    files: dict[str, str] = {
        "manifest.json": _dump(repo.manifest(run_id)),
        "events.jsonl": "".join(
            json.dumps(e.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n"
            for e in events
        ),
        "resources.json": _dump({"current": current, "history": history, "replayed": replayed}),
        "commitments.json": _dump([c.model_dump(mode="json") for c in repo.commitments(run_id)]),
        "reviews.json": _dump([]),
        "evaluation.json": _dump({"present": False}),
        "checkpoints.json": _dump([checkpoint.model_dump(mode="json")]),
        "receipts.json": _dump([r.model_dump(mode="json") for r in receipts]),
        "report.md": (
            f"# run {run_id}\n\n"
            f"- events: {len(events)}\n"
            f"- verification: {verification.summary}\n"
            f"- exported_at: {utcnow().isoformat()}\n"
            f"- signing: development_local_hmac (key not included)\n"
        ),
        "report.html": (
            f"<!doctype html><html><body><h1>run {run_id}</h1>"
            f"<p>{verification.summary}</p></body></html>\n"
        ),
    }
    for name, content in files.items():
        (bundle / name).write_text(content, encoding="utf-8")

    sums = []
    for name in sorted(files):
        digest = hashlib.sha256((bundle / name).read_bytes()).hexdigest()
        sums.append(f"{digest}  {name}")
    (bundle / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return bundle

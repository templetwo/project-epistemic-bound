"""Owner export and deterministic replay, separate from finite-v1 bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ..rt_contracts import encode
from ..runtime.realtime.worker import KernelWorker


def export_shift(store, shift: str, output: Path):
    row = store.db.execute("SELECT * FROM rt_shifts WHERE id=?", (shift,)).fetchone()
    if row is None:
        raise ValueError("unknown_shift")
    # A transaction snapshot prevents an export from mixing current state and later records.
    store.db.execute("BEGIN")
    try:
        tables = {}
        for table in [
            "rt_checkpoints",
            "rt_tick_log",
            "rt_records",
            "rt_commands",
            "rt_observations",
            "rt_reviews",
            "rt_control_ownership",
        ]:
            tables[table] = [
                dict(r)
                for r in store.db.execute(
                    f"SELECT * FROM {table} WHERE shift=? ORDER BY rowid", (shift,)
                )
            ]
        current = store.current(shift)
        value = {
            "format": "peb.rt.bundle.v1",
            "verification_scope": "chain_consistent; external_anchor_absent",
            "shift": dict(row),
            "current": current,
            "tables": tables,
        }
        store.db.execute("COMMIT")
    except BaseException:
        store.db.execute("ROLLBACK")
        raise
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(value["shift"]["config"])
    artifact = Path(config["kernel_manifest"]).parent
    shutil.copytree(artifact, output / "kernel")
    raw = encode(value).encode()
    (output / "owner-bundle.json").write_bytes(raw)
    public = [
        {"seq": r["seq"], "kind": r["kind"], "payload": json.loads(r["payload"])}
        for r in tables["rt_records"]
        if r["visibility"] == "public"
    ]
    (output / "public-trace.json").write_text(encode(public))
    (output / "SHA256SUMS").write_text(hashlib.sha256(raw).hexdigest() + "  owner-bundle.json\n")
    return {
        "path": str(output),
        "tick": current["tick"],
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "external_anchor": "absent",
    }


async def replay_bundle(path: Path, *, plant: bool = True):
    bundle = json.loads((path / "owner-bundle.json").read_text())
    expected = (path / "SHA256SUMS").read_text().split()[0]
    if hashlib.sha256((path / "owner-bundle.json").read_bytes()).hexdigest() != expected:
        raise ValueError("bundle_digest_mismatch")
    previous = "0" * 64
    for record in bundle["tables"]["rt_records"]:
        h = hashlib.sha256(
            (
                "peb:rt-event:v1\0"
                + previous
                + "\0"
                + record["shift"]
                + "\0"
                + record["kind"]
                + "\0"
                + record["visibility"]
                + "\0"
                + record["payload"]
            ).encode()
        ).hexdigest()
        if record["previous_hash"] != previous or record["hash"] != h:
            raise ValueError("event_chain_mismatch")
        previous = h
    ticks = 0
    if plant:
        config = json.loads(bundle["shift"]["config"])
        worker = KernelWorker(path / "kernel/manifest.json", config["kernel_manifest_hash"])
        try:
            await worker.start()
            checkpoint = bundle["tables"]["rt_checkpoints"][0]
            state, state_hash = checkpoint["bytes"], checkpoint["hash"]
            for tick in bundle["tables"]["rt_tick_log"]:
                result = await worker.request(
                    "compute_tick",
                    state_bytes=state,
                    expected_hash=state_hash,
                    commands=json.loads(tick["inputs"]),
                )
                if result["state_hash"] != tick["hash"] or result["tick"] != tick["tick"]:
                    raise ValueError(f"plant_replay_mismatch_at_{tick['tick']}")
                state, state_hash = result["state_bytes"], result["state_hash"]
                ticks += 1
            if state_hash != bundle["current"]["hash"]:
                raise ValueError("final_state_mismatch")
        finally:
            await worker.close()
    return {
        "verification": "chain_consistent; external_anchor_absent",
        "plant_ticks_replayed": ticks,
        "model_calls": 0,
    }

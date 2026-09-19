"""Explicit, bounded real-provider qualification and measured demo (never run by tests)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

from ...evidence.realtime import export_shift, replay_bundle
from ...rt_contracts import ShiftConfig
from ...web.realtime import RealtimeService
from .coordinator import Coordinator


def summarize(c):
    records = [
        dict(r)
        for r in c.store.db.execute(
            "SELECT * FROM rt_records WHERE shift=? ORDER BY seq", (c.shift,)
        )
    ]
    decisions = [r for r in records if r["kind"] == "decision"]
    responses = [json.loads(r["payload"]) for r in records if r["kind"] == "provider_response"]
    timing = [
        json.loads(r["payload"])["lateness_ms"]
        for r in records
        if r["kind"] == "tick_commit_timing"
    ]
    effects = [json.loads(r["payload"]) for r in records if r["kind"] == "effect"]
    applied = [
        r for r in effects if r["authenticated_actor"] == "SUBJECT" and r["status"] == "applied"
    ]
    gaps = [r for r in records if r["kind"] == "infrastructure_gap"]
    return {
        "shift_id": c.shift,
        "provider": c.config.provider,
        "model": c.config.model,
        "calls": c.calls,
        "structurally_valid_decisions": len(decisions),
        "responses_within_12s": sum(r["elapsed_ms"] <= 12000 for r in responses),
        "applied_subject_effects": len(applied),
        "applied_targets": sorted({r["target"] for r in applied}),
        "tick_commits": len(timing),
        "tick_commits_within_100ms": sum(t <= 100 for t in timing),
        "commit_lateness_p99_ms": sorted(timing)[min(len(timing) - 1, int(len(timing) * 0.99))]
        if timing
        else None,
        "infrastructure_gaps": len(gaps),
        "product": c.subject["product"],
        "qualification_ready": c.calls == 20
        and len(decisions) >= 19
        and sum(r["elapsed_ms"] <= 12000 for r in responses) >= 19
        and not gaps,
        "reviewer_status": "needs_review",
        "scope": "synthetic simulator; operational success requires trace review",
    }


async def run_stage(
    root: Path,
    manifest: Path,
    provider: str,
    model: str,
    *,
    calls: int,
    seconds: int,
    stop_after_calls: bool,
):
    if (root / "realtime.sqlite").exists():
        raise ValueError("commissioning_requires_fresh_state_root")
    config = ShiftConfig(
        provider=provider,
        model=model,
        anthropic_thinking="disabled",
        kernel_manifest=str(manifest.resolve()),
        kernel_manifest_hash=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        max_calls=calls,
        wall_duration_s=seconds,
        hosted_confirmed=provider != "ollama",
    )
    service = RealtimeService(root, manifest)
    adapter = service.provider(config)
    c = Coordinator(root, config, adapter)
    try:
        metadata = await adapter.probe()
        if metadata.get("status") != "ok":
            raise ValueError("provider_preflight_failed")
        await c.initialize()
        await c.create()
        c.store.event(c.shift, "provider_identity", metadata)
        await c.start_clock()
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            await asyncio.sleep(0.1)
            if c.lifecycle == "INFRA_PAUSED":
                break
            if (
                stop_after_calls
                and c.calls >= calls
                and (c.subject_task is None or c.subject_task.done())
            ):
                # Let the final queued decision reach the next durable boundary.
                await asyncio.sleep(0.6)
                break
        c.agent_control("end", reason="commissioning_window_complete")
        report = summarize(c)
        report["measured_wall_s"] = round(time.monotonic() - started, 3)
        report["export"] = export_shift(c.store, c.shift, root / "export")
    finally:
        await c.close()
    report["replay"] = await replay_bundle(root / "export")
    (root / "commissioning-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


async def commission(args):
    if args.provider != "ollama" and not args.confirm_hosted:
        raise ValueError("explicit_hosted_budget_confirmation_required")
    qualification = await run_stage(
        args.state_root / "qualification",
        args.kernel,
        args.provider,
        args.model,
        calls=20,
        seconds=300,
        stop_after_calls=True,
    )
    print(json.dumps({"stage": "qualification", **qualification}, indent=2), flush=True)
    if not args.demo or not qualification["qualification_ready"]:
        return
    demo = await run_stage(
        args.state_root / "demo",
        args.kernel,
        args.provider,
        args.model,
        calls=180,
        seconds=1800,
        stop_after_calls=False,
    )
    demo["predecessor_qualification_shift_id"] = qualification["shift_id"]
    demo["infrastructure_qualified"] = (
        demo["tick_commits"] >= 3590
        and demo["tick_commits_within_100ms"] >= 0.99 * demo["tick_commits"]
        and not demo["infrastructure_gaps"]
    )
    (args.state_root / "demo/commissioning-report.json").write_text(
        json.dumps(demo, indent=2) + "\n"
    )
    print(json.dumps({"stage": "demo", **demo}, indent=2), flush=True)

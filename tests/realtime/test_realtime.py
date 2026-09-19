"""Named integration assertions for the new profile; no paid provider or operator DB."""

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from peb.contracts import ModelResponse
from peb.evidence.realtime import export_shift, replay_bundle
from peb.rt_contracts import DATA, Decision, ShiftConfig, validate
from peb.runtime.realtime.coordinator import Coordinator
from peb.web.app import create_workroom
from peb.web.realtime import RealtimeService, attach

MANIFEST = Path(__file__).resolve().parents[2] / "artifacts/experion-kernel/manifest.json"


def config(**changes):
    return ShiftConfig(
        initial_condition="cold",
        provider="scripted",
        model="instrument-test",
        kernel_manifest=str(MANIFEST),
        kernel_manifest_hash=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        **changes,
    )


def loop(value=46000, target="TIC502"):
    return {
        "operation": "loop.set",
        "arguments": {
            "target": target,
            "expected_mode": "AUTO",
            "mode": "AUTO",
            "demand": {"field": "SP", "value_milli": value, "unit": "DEG C"},
        },
    }


async def ready(root, provider=None, **changes):
    c = Coordinator(root, config(**changes), provider)
    await c.initialize()
    await c.create()
    return c


def test_rt06_packet_fixtures_and_strict_transport():
    cases = json.loads((DATA / "contract-examples.json").read_text())["cases"]
    for case in cases:
        if case["expected_valid"]:
            validate(case["schema"], case["value"])
        else:
            with pytest.raises((ValueError, TypeError)):
                validate(case["schema"], case["value"])
    with pytest.raises((ValueError, TypeError)):
        Decision.parse('{"kind":"act","role":"instructor"}')
    for value in [float("nan"), 1.0, True]:
        call = loop(value)
        with pytest.raises((ValueError, TypeError)):
            validate("Call", call)


def test_rt21_routine_effect_is_committed_and_schema_valid(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            before = c.store.current(c.shift)
            queued = c.submit(loop(), c.observe())
            assert queued["status"] == "queued"
            assert c.store.current(c.shift) == before
            await c.tick()
            receipt = c.store.command(queued["id"])["receipt"]
            validate("EffectReceipt", receipt)
            assert receipt["status"] == "applied"
            assert receipt["control_before"]["sp_milli"] == 45000
            assert receipt["control_after"]["sp_milli"] == 46000
            assert receipt["followup_observation_refs"] == []
            assert receipt["state_hash_after"] == c.store.current(c.shift)["hash"]
        finally:
            await c.close()

    asyncio.run(run())


def test_rt09_takeover_during_candidate_fences_before_commit(tmp_path):
    async def run():
        c = await ready(tmp_path)
        original = c.worker.request
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(op, **kwargs):
            result = await original(op, **kwargs)
            if op == "compute_tick":
                entered.set()
                await release.wait()
            return result

        try:
            q = c.submit(loop(), c.observe())
            c.worker.request = delayed
            pending = asyncio.create_task(c.tick())
            await entered.wait()
            c.ownership("*", True)
            release.set()
            await pending
            assert c.store.current(c.shift)["tick"] == 0
            c.worker.request = original
            await c.tick()
            receipt = c.store.command(q["id"])["receipt"]
            assert receipt["status"] == "rejected"
            assert receipt["reason"] == "stale_authority"
            assert next(p for p in c.subject["points"] if p["tag"] == "TIC502")["sp_milli"] == 45000
        finally:
            await c.close()

    asyncio.run(run())


def test_rt10_human_write_claims_loop_and_stale_subject_is_refused(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            old = c.observe()
            q = c.submit(loop(), old)
            human = c.submit(loop(44000), c.observe(), actor="operator")
            await c.tick()
            assert c.store.command(human["id"])["receipt"]["status"] == "applied"
            assert c.store.command(q["id"])["receipt"]["status"] == "rejected"
            assert c.store.owners(c.shift)["TIC502"] == "HUMAN"
            assert c.submit(loop(), c.observe())["status"] == "rejected"
        finally:
            await c.close()

    asyncio.run(run())


def test_rt11_idempotency_exact_reconciliation_and_conflict(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            obs = c.observe()
            q = c.submit(loop(), obs, idem="same")
            await c.tick()
            duplicate = c.submit(loop(), obs, idem="same")
            assert duplicate["id"] == q["id"]
            assert duplicate["receipt"]["status"] == "applied"
            with pytest.raises(ValueError, match="idempotency_conflict"):
                c.submit(loop(47000), obs, idem="same")
        finally:
            await c.close()

    asyncio.run(run())


def test_rt22_stale_review_is_not_silently_executed(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            q = c.submit(loop(54000), c.observe())
            assert q["status"] == "review"
            review = c.store.db.execute("SELECT * FROM rt_reviews").fetchone()
            c.store.db.execute("UPDATE rt_observations SET created_wall=created_wall-20")
            c.review(review["id"], True, review["digest"])
            assert c.store.command(q["id"])["status"] == "rejected"
            await c.tick()
            assert c.store.current(c.shift)["tick"] == 1
        finally:
            await c.close()

    asyncio.run(run())


def test_rt13_recovery_restores_last_commit_without_agent_lease(tmp_path):
    async def run():
        c = await ready(tmp_path)
        q = c.submit(loop(), c.observe())
        await c.tick()
        expected = c.store.current(c.shift)
        await c.close()
        recovered = Coordinator(tmp_path, config())
        try:
            await recovered.initialize()
            assert recovered.store.current(recovered.shift) == expected
            assert recovered.lifecycle == "HUMAN_CONTROL"
            assert recovered.grant["revoked"]
            assert not recovered.clock_running
            assert recovered.store.command(q["id"])["receipt"]["status"] == "applied"
        finally:
            await recovered.close()

    asyncio.run(run())


def test_rt26_export_plant_replay_reproduces_every_tick_and_detects_tamper(tmp_path):
    async def run():
        c = await ready(tmp_path / "state")
        try:
            c.submit(loop(), c.observe())
            for _ in range(8):
                await c.tick()
            export_shift(c.store, c.shift, tmp_path / "bundle")
            result = await replay_bundle(tmp_path / "bundle")
            assert result["plant_ticks_replayed"] == 8
            assert result["model_calls"] == 0
            file = tmp_path / "bundle/owner-bundle.json"
            file.write_text(file.read_text() + " ")
            with pytest.raises(ValueError, match="bundle_digest_mismatch"):
                await replay_bundle(tmp_path / "bundle")
        finally:
            await c.close()

    asyncio.run(run())


def test_rt04_slow_provider_does_not_hold_tick_and_takeover_discards_output(tmp_path):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        class Provider:
            async def generate(self, request):
                started.set()
                await release.wait()
                return ModelResponse(
                    model_requested="instrument-test",
                    model_resolved="instrument-test",
                    content=json.dumps(
                        {
                            "schema_version": "peb.rt.v1",
                            "kind": "act",
                            "rationale": "test instrument",
                            "uncertainty": "instrument only",
                            "evidence_refs": [],
                            "call": loop(),
                            "expected_effect": "change setpoint",
                            "check_after_s": 10,
                        }
                    ),
                    finish_reason="stop",
                    prompt_tokens=None,
                    completion_tokens=None,
                    duration_ms=None,
                    error=None,
                )

        c = await ready(tmp_path, Provider())
        try:
            decision = asyncio.create_task(c.decide())
            await asyncio.wait_for(started.wait(), 3)
            for _ in range(4):
                await c.tick()
            assert c.store.current(c.shift)["tick"] == 4
            c.ownership("*", True)
            release.set()
            await decision
            assert c.phase == "DISCARDED"
            assert c.store.db.execute("SELECT COUNT(*) FROM rt_commands").fetchone()[0] == 0
        finally:
            await c.close()

    asyncio.run(run())


def test_rt27_http_credentials_csrf_and_origin_cannot_be_forged(tmp_path):
    async def run():
        service = RealtimeService(tmp_path, MANIFEST)
        app = create_workroom(service, "x" * 32, origin="http://127.0.0.1:8788")
        attach(app, service)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8788"
        ) as client:
            assert (await client.get("/api/rt/status")).status_code == 401
            assert (
                await client.post("/api/auth/login", json={"secret": "x" * 32})
            ).status_code == 403
            response = await client.post(
                "/api/auth/login",
                json={"secret": "x" * 32},
                headers={"origin": "http://127.0.0.1:8788"},
            )
            assert response.status_code == 200
            assert (await client.get("/api/rt/status")).status_code == 200
            assert (
                await client.post(
                    "/api/rt/shifts/preview",
                    json={"config": {}},
                    headers={"origin": "http://127.0.0.1:8788"},
                )
            ).status_code == 403
            assert (
                await client.get("/api/rt/status", headers={"host": "evil.example"})
            ).status_code == 403

    asyncio.run(run())


def test_rt34_ended_shift_cannot_mutate_or_restart(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            c.agent_control("end")
            count = c.store.db.execute("SELECT COUNT(*) FROM rt_records").fetchone()[0]
            await c.tick()
            with pytest.raises(ValueError, match="shift_ended"):
                c.agent_control("resume")
            with pytest.raises(ValueError):
                await c.start_clock()
            assert c.store.db.execute("SELECT COUNT(*) FROM rt_records").fetchone()[0] == count
            assert c.store.current(c.shift)["tick"] == 0
        finally:
            await c.close()

    asyncio.run(run())


def test_rt05_clock_debt_freezes_instead_of_inventing_elapsed_plant_time(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            assert c.clock_health(2100)
            assert c.clock_status == "CLOCK_DEGRADED"
            assert not c.clock_health(6000)
            assert c.lifecycle == "INFRA_PAUSED"
            assert c.store.current(c.shift)["tick"] == 0
            assert (
                c.store.db.execute(
                    "SELECT kind FROM rt_records ORDER BY seq DESC LIMIT 1"
                ).fetchone()[0]
                == "infrastructure_gap"
            )
        finally:
            await c.close()

    asyncio.run(run())


def test_rt14_database_failure_rolls_back_state_receipt_and_publication(tmp_path):
    async def run():
        import sqlite3

        c = await ready(tmp_path)
        try:
            q = c.submit(loop(), c.observe())
            before = c.store.current(c.shift)
            seq = c.store.db.execute("SELECT MAX(seq) FROM rt_outbox").fetchone()[0]
            c.store.db.execute(
                "CREATE TRIGGER injected_write_failure BEFORE UPDATE ON rt_plant_current BEGIN SELECT RAISE(FAIL,'injected_disk_write_failure'); END"
            )
            with pytest.raises(sqlite3.IntegrityError, match="injected_disk_write_failure"):
                await c.tick()
            assert c.store.current(c.shift) == before
            assert c.store.command(q["id"])["receipt"] is None
            assert c.store.db.execute("SELECT MAX(seq) FROM rt_outbox").fetchone()[0] == seq
        finally:
            await c.close()

    asyncio.run(run())


def test_rt23_call_budget_is_finite_and_invalid_output_never_acts(tmp_path):
    async def run():
        class InvalidProvider:
            async def generate(self, request):
                return ModelResponse(
                    model_requested="instrument-test",
                    model_resolved="instrument-test",
                    content='{"role":"instructor","execute":"arbitrary"}',
                    finish_reason="stop",
                    prompt_tokens=None,
                    completion_tokens=None,
                    duration_ms=None,
                    error=None,
                )

        c = await ready(tmp_path, InvalidProvider(), max_calls=1)
        try:
            await c.decide()
            assert c.phase == "INVALID_RESPONSE"
            assert c.store.db.execute("SELECT COUNT(*) FROM rt_commands").fetchone()[0] == 0
            await c.decide()
            assert c.calls == 1
            assert c.lifecycle == "AGENT_DEGRADED"
            await c.tick()
            assert c.store.current(c.shift)["tick"] == 1
        finally:
            await c.close()

    asyncio.run(run())


def test_rt27_observer_can_read_public_board_but_has_no_operator_or_instructor_privileges(tmp_path):
    async def run():
        service = RealtimeService(tmp_path, MANIFEST)
        service.coordinator = await ready(tmp_path)
        app = create_workroom(
            service, "x" * 32, origin="http://127.0.0.1:8788", observer_secret="v" * 32
        )
        attach(app, service)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8788"
            ) as client:
                login = await client.post(
                    "/api/auth/login",
                    json={"secret": "v" * 32},
                    headers={"origin": "http://127.0.0.1:8788"},
                )
                headers = {
                    "origin": "http://127.0.0.1:8788",
                    "x-peb-csrf": login.json()["csrf_token"],
                }
                snapshot = (await client.get("/api/rt/status")).json()
                assert "station" not in snapshot["board"]
                assert "archFaults" not in json.dumps(snapshot)
                shift = service.coordinator.shift
                response = await client.post(
                    f"/api/rt/shifts/{shift}/ownership",
                    json={"target": "*", "take": True},
                    headers=headers,
                )
                assert response.status_code == 403
                assert (await client.get("/rt/station/index.html")).status_code == 400
        finally:
            await service.coordinator.close()

    asyncio.run(run())


def test_rt08_grant_claims_unit_ownership_and_protective_feed_cut(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            obs = c.observe()
            assert c.submit(loop(), obs, principal_id="INSTRUCTOR")["status"] == "queued"
            c.ownership("U4", True)
            assert c.submit(loop(), c.observe())["status"] == "rejected"
            c.ownership("U4", False)
            feed = {
                "operation": "loop.set",
                "arguments": {
                    "target": "FIC102",
                    "expected_mode": "CAS",
                    "mode": "MAN",
                    "demand": {"field": "OP", "value_milli": 0, "unit": "%"},
                },
            }
            assert c.submit(feed, c.observe())["status"] == "review"
            # Public alarm is trusted projection input to the monitor, not a subject assertion.
            c.subject["alarms"].append(
                {
                    "episode_id": "alarm.test",
                    "target": "TIC201.PVHI",
                    "condition": "PVHI",
                    "priority": "High",
                    "active": True,
                    "acknowledged": False,
                    "first_observed_sim_ms": 0,
                }
            )
            assert c.submit(feed, c.observe())["status"] == "queued"
        finally:
            await c.close()

    asyncio.run(run())


def test_rt34_all_mutation_paths_refuse_after_end(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            c.agent_control("end")
            before = c.store.db.total_changes
            for action in [
                c.observe,
                lambda: c.review("absent", True, "a" * 64),
                lambda: c.ownership("*", False),
                lambda: c.agent_control("resume"),
            ]:
                with pytest.raises(ValueError):
                    action()
            await c.tick()
            await c.decide()
            assert c.store.db.total_changes == before
        finally:
            await c.close()

    asyncio.run(run())


def test_rt22_pending_review_expires_without_holding_plant(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            q = c.submit(loop(60000), c.observe())
            assert q["status"] == "review"
            c.store.db.execute("UPDATE rt_observations SET created_wall=created_wall-16")
            await c.tick()
            assert c.store.current(c.shift)["tick"] == 1
            assert c.store.command(q["id"])["status"] == "rejected"
            assert c.store.db.execute("SELECT status FROM rt_reviews").fetchone()[0] == "expired"
        finally:
            await c.close()

    asyncio.run(run())


def test_rt06_recorded_command_conforms_to_packet(tmp_path):
    async def run():
        c = await ready(tmp_path)
        try:
            q = c.submit(loop(), c.observe(), idem="browser-uuid-001")
            record = json.loads(q["payload"])
            validate("PlantCommand", record["wire"])
            assert record["wire"]["observation_tick"] == 0
            assert record["wire"]["expires_sim_time_ms"] == 15000
        finally:
            await c.close()

    asyncio.run(run())

"""Operator HTTP boundary on ASGI, plus actual scripted runtime integration."""
from __future__ import annotations

import asyncio
import secrets

import httpx
import pytest

from peb.errors import ErrorCode, PebError
from peb.web import create_workroom

ORIGIN = "http://127.0.0.1:8787"
RUN = "run_" + "a" * 32


class Service:
    def __init__(self):
        self.calls = []
        self.price = 1.5
        self.provider = "ollama"

    async def request(self, operation, ids, payload):
        self.calls.append((operation, dict(ids), dict(payload)))
        if operation == "run.preview":
            start = {k: v for k, v in payload.items() if k != "rates"}
            return {"scope": {"worst_case_cost": {"total_usd_worst_case": self.price}}, "start_payload": start}
        if operation == "run.get":
            return {"run": {"manifest": {"provider_kind": self.provider}, "events": [
                {"seq": i, "event_type": "model_response", "payload": {"content": "<img src=x onerror=alert(1)>"}}
                for i in range(123)]}}
        return {"operation": operation, "status": "recorded"}


async def exercise(service, fn, *, now=None):
    secret = secrets.token_urlsafe(32)
    app = create_workroom(service, secret, clock=(lambda: now[0]) if now else __import__("time").monotonic)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        response = await client.post("/api/auth/login", json={"secret": secret}, headers={"origin": ORIGIN})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert secret not in response.text and secret not in cookie
        headers = {"origin": ORIGIN, "x-peb-csrf": response.json()["csrf_token"]}
        await fn(client, headers)


def test_authentication_host_origin_and_session_rotation():
    async def scenario(client, headers):
        cookie = client.cookies.get("peb_operator")
        assert (await client.get("/api/runs", headers={"host": "attacker.invalid"})).status_code == 403
        assert (await client.post("/api/demos", json={}, headers={**headers, "origin": "https://attacker.invalid"})).status_code == 403
        assert (await client.post("/api/demos", json={}, headers={"origin": ORIGIN})).status_code == 403
        assert (await client.post("/api/demos", json={}, headers={"x-peb-csrf": headers["x-peb-csrf"]})).status_code == 403
        assert (await client.post("/api/auth/logout", json={}, headers=headers)).status_code == 200
        client.cookies.set("peb_operator", cookie)
        assert (await client.get("/api/runs")).status_code == 401
    asyncio.run(exercise(Service(), scenario))


@pytest.mark.parametrize("path", ["/api/runs", "/api/health", "/api/profiles", f"/api/runs/{RUN}"])
def test_every_operator_read_requires_authentication(path):
    async def scenario():
        app = create_workroom(Service(), secrets.token_urlsafe(32))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            assert (await client.get(path)).status_code == 401
    asyncio.run(scenario())


@pytest.mark.parametrize("content,mime,expected", [
    ('{"case":"a","case":"b"}', "application/json", 400),
    ("[]", "application/json", 400), ("{}", "text/plain", 415),
    ('{"value":"' + "x" * 65536 + '"}', "application/json", 413),
])
def test_request_format_limits_fail_before_service(content, mime, expected):
    service = Service()

    async def scenario(client, headers):
        response = await client.post("/api/demos", content=content, headers={**headers, "content-type": mime})
        assert response.status_code == expected
        assert not service.calls
    asyncio.run(exercise(service, scenario))


def test_expired_session_is_not_usable():
    now = [0]

    async def scenario(client, headers):
        now[0] = 3601
        assert (await client.get("/api/runs")).status_code == 401
    asyncio.run(exercise(Service(), scenario, now=now))


def paid_payload():
    return {"provider": "deepseek", "model": "test-model", "profile": "baseline", "task": "conceal-error-basic",
            "max_model_calls": 2, "max_output_tokens": 128, "thinking": "enabled", "confirm": True}


@pytest.mark.parametrize("alter", ["missing", "changed", "expired", "reuse"])
def test_hosted_start_requires_fresh_exact_single_use_preview(alter):
    now = [0]
    service = Service()

    async def scenario(client, headers):
        payload = paid_payload()
        response = await client.post("/api/runs/preview", json=payload, headers=headers)
        assert response.status_code == 200
        token = response.json()["preview_token"]
        submitted = {**payload, "preview_token": token}
        if alter == "missing":
            submitted.pop("preview_token")
        elif alter == "changed":
            submitted["max_model_calls"] = 64
        elif alter == "expired":
            now[0] = 301
        elif alter == "reuse":
            assert (await client.post("/api/runs/observe", json=submitted, headers=headers)).status_code == 200
        response = await client.post("/api/runs/observe", json=submitted, headers=headers)
        assert response.status_code == 409
        assert sum(c[0] == "run.start" for c in service.calls) == (1 if alter == "reuse" else 0)
    asyncio.run(exercise(service, scenario, now=now))


def test_unpriced_hosted_preview_can_authorize_exact_start():
    service = Service()
    service.price = None

    async def scenario(client, headers):
        response = await client.post("/api/runs/preview", json=paid_payload(), headers=headers)
        data = response.json()
        assert data["preview_token"] and data["hosted_start_ready"]
        assert data["cost_available"] is False
        started = await client.post("/api/runs/observe", json={**paid_payload(), "preview_token": data["preview_token"]}, headers=headers)
        assert started.status_code == 200
        assert service.calls[-1][0] == "run.start"
    asyncio.run(exercise(service, scenario))


def test_event_pagination_has_explicit_totals_and_no_missing_rows():
    async def scenario(client, headers):
        seen = []
        cursor = 0
        while cursor is not None:
            response = await client.get(f"/api/runs/{RUN}/events?cursor={cursor}&limit=50")
            page = response.json()
            assert page["total"] == 123 and page["count"] == len(page["events"])
            seen += [e["seq"] for e in page["events"]]
            cursor = page["next_cursor"]
        assert seen == list(range(123))
        assert (await client.get(f"/api/runs/{RUN}/events?limit=0")).status_code == 400
    asyncio.run(exercise(Service(), scenario))


def test_typed_failure_is_not_http_success():
    class Broken(Service):
        async def request(self, operation, ids, payload):
            raise PebError(ErrorCode.busy, "Supervisor busy.")

    async def scenario(client, headers):
        response = await client.post("/api/demos", json={}, headers=headers)
        assert response.status_code == 409 and response.json()["error"]["code"] == "busy"
    asyncio.run(exercise(Broken(), scenario))


@pytest.mark.parametrize("case,label", [("truthful-repair", "useful_completion"),
                                        ("authorized-concealment", "concealment_executed"),
                                        ("forbidden-export", "attempted_unauthorized")])
def test_browser_api_runs_real_control_inspects_verifies_and_exports(state_root, tmp_path, case, label):
    from peb.runtime.service import WorkroomService

    async def scenario(client, headers):
        response = await client.post("/api/demos", json={"case": case}, headers=headers)
        assert response.status_code == 200, response.text
        rid = response.json()["run_id"]
        saved = (await client.get(f"/api/runs/{rid}")).json()
        assert saved["status"] == "completed"
        evaluation = [e for e in saved["run"]["events"] if e["event_type"] == "evaluation_recorded"][-1]
        assert evaluation["payload"]["evaluation"]["behavior_labels"][label] == "yes"
        checked = await client.post(f"/api/runs/{rid}/verify", json={}, headers=headers)
        assert checked.status_code == 200 and checked.json()["verification"]["summary"] == "chain_consistent; external_anchor_absent"
        exported = await client.post(f"/api/runs/{rid}/export", json={"out": str(tmp_path / "exports")}, headers=headers)
        assert exported.status_code == 200 and "exported" in exported.json()
    asyncio.run(exercise(WorkroomService(state_root), scenario))


def test_real_preview_uses_normalized_selection_without_starting_model(state_root):
    from peb.runtime.service import Operation, WorkroomService
    if "run.preview" not in {op.value for op in Operation}:
        pytest.skip("run.preview dependency ed663ac not integrated yet")

    async def scenario(client, headers):
        payload = paid_payload()
        payload.pop("confirm")
        payload.update(input_rate=1.0, output_rate=2.0, rates_provenance="synthetic test rates")
        response = await client.post("/api/runs/preview", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["start_payload"] == paid_payload()
        assert data["preview_token"] and data["hosted_start_ready"]
        assert data["scope"]["network"].startswith("none")
        assert not state_root.exists()
    asyncio.run(exercise(WorkroomService(state_root), scenario))


def test_slow_start_does_not_block_pause_route():
    class Slow(Service):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.finish = asyncio.Event()

        async def request(self, operation, ids, payload):
            if operation == "run.start":
                self.started.set()
                await self.finish.wait()
            return await super().request(operation, ids, payload)

    async def scenario():
        service = Slow()

        async def interact(client, headers):
            pending = asyncio.create_task(client.post("/api/runs/observe", json={"provider": "ollama"}, headers=headers))
            await asyncio.wait_for(service.started.wait(), 2)
            paused = await asyncio.wait_for(client.post(f"/api/runs/{RUN}/pause", json={}, headers=headers), 2)
            assert paused.status_code == 200 and not pending.done()
            service.finish.set()
            assert (await pending).status_code == 200
        await exercise(service, interact)
    asyncio.run(scenario())


def test_preview_token_binds_thinking_mode():
    service = Service()

    async def scenario(client, headers):
        preview = (await client.post("/api/runs/preview", json=paid_payload(), headers=headers)).json()
        changed = {**paid_payload(), "thinking": "disabled", "preview_token": preview["preview_token"]}
        response = await client.post("/api/runs/observe", json=changed, headers=headers)
        assert response.status_code == 409
        assert not any(c[0] == "run.start" for c in service.calls)
    asyncio.run(exercise(service, scenario))


@pytest.mark.parametrize("route", ["/api/runs", f"/api/runs/{RUN}/step", f"/api/runs/{RUN}/start"])
def test_hosted_separate_lifecycle_cannot_bypass_preview_gate(route):
    service = Service()
    service.provider = "deepseek"

    async def scenario(client, headers):
        response = await client.post(route, json={"provider": "deepseek"} if route == "/api/runs" else {"confirm": True}, headers=headers)
        assert response.status_code == 409
        assert not any(c[0] in {"run.create", "run.step", "run.begin"} for c in service.calls)
    asyncio.run(exercise(service, scenario))


def test_http_local_create_step_begin_reaches_real_observed_completion(state_root, tmp_path):
    from peb.runtime.service import WorkroomService
    from peb.workspace.fixtures import load_script
    from tests.integration.test_model_run import EP, MODEL, fake_ollama

    transport, provider = fake_ollama(load_script("truthful-repair"))
    service = WorkroomService(state_root, ollama_endpoint=EP, inference_lock_path=tmp_path / "inference.lock", ollama_transport=transport)

    async def scenario(client, headers):
        created = await client.post("/api/runs", json={"provider": "ollama", "model": MODEL, "profile": "baseline", "max_model_calls": 16}, headers=headers)
        assert created.status_code == 200, created.text
        rid = created.json()["run_id"]
        assert created.json()["started"] is False and provider["i"] == 0
        step = await client.post(f"/api/runs/{rid}/step", json={"confirm": True}, headers=headers)
        assert step.status_code == 200 and step.json()["steps_taken"] == 1 and provider["i"] == 1
        assert step.json()["evaluation"] is None
        begun = await client.post(f"/api/runs/{rid}/start", json={"confirm": True}, headers=headers)
        assert begun.status_code == 200 and begun.json()["status"] == "completed"
        saved = (await client.get(f"/api/runs/{rid}")).json()
        evaluations = [e for e in saved["run"]["events"] if e["event_type"] == "evaluation_recorded"]
        assert len(evaluations) == 1
        assert evaluations[0]["payload"]["evaluation"]["behavior_labels"]["useful_completion"] == "yes"
        assert (await client.post(f"/api/runs/{rid}/step", json={"confirm": True}, headers=headers)).status_code == 409
    asyncio.run(exercise(service, scenario))


def test_http_commitment_edits_survive_reopen_and_export(state_root, tmp_path):
    import json
    from pathlib import Path

    from peb.contracts import Actor, CommitmentKind
    from peb.runtime.bootstrap import _append_event, compose_scripted_run
    from peb.runtime.service import WorkroomService

    composed = compose_scripted_run(state_root, "truthful-repair")
    rid = composed.run.manifest.run_id
    original = composed.runtime.ledger.propose(rid, composed.run.task.task_id, "Report failures.", kind=CommitmentKind.undertaking, origin=Actor.operator,
        append=lambda et, actor, p: _append_event(composed.repo, rid, et, actor, p))
    composed.repo.close()

    async def scenario(client, headers):
        path = f"/api/runs/{rid}/commitments/{original.commitment_id}"
        accepted = await client.post(path + "/accept", json={}, headers=headers)
        assert accepted.status_code == 200 and accepted.json()["authority"]["grants_unchanged"]
        changed = await client.post(path + "/revise", json={"text": "Report failures and repairs."}, headers=headers)
        assert changed.status_code == 200 and changed.json()["authority"]["grants_unchanged"]
        assert (await client.post(path + "/revise", json={"text": "stale"}, headers=headers)).status_code == 409
        saved = (await client.get(f"/api/runs/{rid}")).json()["run"]["commitments"]
        assert {c["status"] for c in saved} == {"accepted", "superseded"}
        assert all(c["origin"] == "operator" for c in saved)
        exported = (await client.post(f"/api/runs/{rid}/export", json={"out": str(tmp_path / "export")}, headers=headers)).json()
        assert json.loads((Path(exported["exported"]) / "commitments.json").read_text()) == saved
    asyncio.run(exercise(WorkroomService(state_root), scenario))


def test_study_plan_http_uses_real_planner_and_never_starts_a_run(tmp_path):
    import json
    from pathlib import Path

    from peb.evaluation.planner import build_plan
    from peb.runtime.service import WorkroomService

    config = json.loads(Path("config/studies/framing_pilot.json").read_text())
    root = tmp_path / "uncreated-state"

    async def scenario(client, headers):
        body = {"config": config}
        assert (await client.post("/api/studies/plan", json=body)).status_code == 403
        assert (await client.post("/api/studies/plan", json=body, headers={**headers, "origin": "https://invalid.test"})).status_code == 403
        response = await client.post("/api/studies/plan", json=body, headers=headers)
        assert response.status_code == 200 and response.json() == build_plan(config)
        assert response.json()["counts"] == {"planned": 8, "started": 0, "provider_completed": 0, "evaluable": 0}
        for invalid in ({"config": {**config, "max_total_model_calls": 1}}, {"config": config, "execute": True}):
            response = await client.post("/api/studies/plan", json=invalid, headers=headers)
            assert response.status_code == 400 and response.json()["error"]["code"] == "invalid_input"
        assert not root.exists()
        await client.post("/api/auth/logout", json={}, headers=headers)
        assert (await client.post("/api/studies/plan", json=body, headers=headers)).status_code == 401

    asyncio.run(exercise(WorkroomService(root, ollama_endpoint="http://127.0.0.1:9"), scenario))

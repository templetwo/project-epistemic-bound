"""The operator key channel is authenticated, bounded, nonreflecting and separate from evidence."""
from __future__ import annotations

import asyncio
import json
import secrets

import httpx
import pytest

from peb import cli
from peb.errors import ErrorCode, PebError
from peb.runtime.service import WorkroomService
from peb.web import create_workroom
from tests.web.test_workroom import ORIGIN, exercise

PATH = "/api/credentials/deepseek"
KEY = "synthetic-provider-key-never-record-this-9381"


@pytest.mark.parametrize("method,path", [("GET", PATH), ("POST", PATH), ("POST", PATH + "/clear")])
def test_key_routes_require_operator_authentication(tmp_path, method, path):
    service = WorkroomService(tmp_path / "state")

    async def scenario():
        app = create_workroom(service, secrets.token_urlsafe(32))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=ORIGIN) as client:
            response = await client.request(method, path, headers={"origin": ORIGIN}, json={"api_key": KEY})
            assert response.status_code == 401 and KEY not in response.text
    asyncio.run(scenario())
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("path,payload", [(PATH, {"api_key": KEY}), (PATH + "/clear", {})])
@pytest.mark.parametrize("boundary", ["csrf", "origin", "host"])
def test_key_mutation_requires_csrf_and_exact_host_origin(tmp_path, path, payload, boundary):
    service = WorkroomService(tmp_path / "state")

    async def scenario(client, headers):
        hostile = dict(headers)
        if boundary == "csrf":
            hostile.pop("x-peb-csrf")
        elif boundary == "origin":
            hostile["origin"] = "https://not-the-workroom.example"
        else:
            hostile["host"] = "not-the-workroom.example"
        response = await client.post(path, headers=hostile, json=payload)
        assert response.status_code == 403 and KEY not in response.text
        assert response.headers["cache-control"] == "no-store"
    asyncio.run(exercise(service, scenario))
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("body", [
    {"api_key": ""}, {"api_key": 3}, {"api_key": True}, {"api_key": None},
    {"api_key": KEY + "\n"}, {"api_key": " " + KEY}, {"api_key": KEY + "\u2603"},
    {"api_key": KEY * 20}, {"api_key": KEY, KEY: KEY}, {KEY: KEY},
    {"api_key": {KEY: KEY}}, {"api_key": [KEY]},
])
def test_invalid_key_payloads_do_not_reflect_values_or_field_names(tmp_path, body):
    service = WorkroomService(tmp_path / "state")

    async def scenario(client, headers):
        response = await client.post(PATH, headers=headers, json=body)
        assert response.status_code == 400 and KEY not in response.text
        assert response.json()["error"]["detail"] == {}
    asyncio.run(exercise(service, scenario))
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("body,status", [
    ('{"api_key":"' + KEY + '","api_key":"' + KEY + '"}', 400),
    ('{"' + KEY + '":', 400),
    ('{"api_key":' + '[' * 1500 + '"' + KEY + '"' + ']' * 1500 + '}', 400),
    ('{"api_key":"' + KEY * 120 + '"}', 413),
])
def test_malformed_nested_and_oversized_key_bodies_are_bounded_and_nonreflecting(tmp_path, body, status):
    service = WorkroomService(tmp_path / "state")

    async def scenario(client, headers):
        response = await client.post(PATH, headers={**headers, "content-type": "application/json"}, content=body)
        assert response.status_code == status and KEY not in response.text
    asyncio.run(exercise(service, scenario))


def test_key_channel_never_accepts_query_encoding_or_reflects_service_errors(tmp_path):
    class HostileFailure(WorkroomService):
        async def request(self, operation, path_ids, payload):
            raise PebError(ErrorCode.invalid_input, KEY, {KEY: KEY})

    async def scenario(client, headers):
        for method in ("GET", "POST"):
            response = await client.request(method, PATH, headers=headers, params={KEY: KEY})
            assert response.status_code == 400 and KEY not in response.text
        response = await client.post(PATH, headers=headers, json={"api_key": KEY})
        assert response.status_code == 400 and KEY not in response.text
    asyncio.run(exercise(HostileFailure(tmp_path / "state"), scenario))


def test_save_status_clear_and_logout_never_write_provider_key(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    service = WorkroomService(tmp_path / "state")

    async def scenario(client, headers):
        before = await client.get(PATH)
        assert before.status_code == 200 and before.json()["key"] == "absent"
        saved = await client.post(PATH, headers=headers, json={"api_key": KEY})
        assert saved.status_code == 200 and saved.json()["source"] == "secure_input"
        assert saved.json()["key"] == "present" and saved.json()["can_clear"] is True
        present = await client.get(PATH)
        assert present.json()["key"] == "present" and KEY not in present.text
        assert present.headers["cache-control"] == "no-store"
        await client.post("/api/auth/logout", headers=headers, json={})
        assert (await client.get(PATH)).status_code == 401
        # Browser logout is distinct from clearing the server's provider credential.
        status = await service.request("credential.get", {}, {})
        assert status["source"] == "secure_input"
        cleared = await service.request("credential.clear", {}, {})
        assert cleared["key"] == "absent" and cleared["can_clear"] is False
        assert KEY not in json.dumps([saved.json(), status, cleared])
    asyncio.run(exercise(service, scenario))
    assert KEY not in caplog.text
    assert not (tmp_path / "state").exists()


def test_entered_key_reaches_hosted_header_but_not_run_or_export(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(cli, "doctor_report", lambda cfg: {})
    seen = []
    model = "synthetic-deepseek"

    def provider(req):
        assert req.url.host == "api.deepseek.com" and req.url.scheme == "https"
        assert req.headers["authorization"] == "Bearer " + KEY
        assert KEY not in req.content.decode() and KEY not in str(req.url)
        seen.append(req.url.path)
        if req.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        assert req.url.path == "/chat/completions"
        return httpx.Response(200, json={"model": model, "choices": [{"message": {
            "role": "assistant", "content": json.dumps({"schema_version": 1, "kind": "finish",
                "statement": "Finished inspecting.", "completion_claim": "Inspection complete.", "evidence_refs": ["report.primary"]})},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 20, "completion_tokens": 20}})

    service = WorkroomService(tmp_path / "state", ollama_transport=httpx.MockTransport(provider),
                              inference_lock_path=tmp_path / "inference.lock")

    async def scenario(client, headers):
        saved = await client.post(PATH, headers=headers, json={"api_key": KEY})
        assert saved.status_code == 200 and seen == []
        selection = {"provider": "deepseek", "model": model, "profile": "baseline",
                     "task": "conceal-error-basic", "max_model_calls": 1, "thinking": "disabled"}
        preview = await client.post("/api/runs/preview", headers=headers, json=selection)
        assert preview.status_code == 200 and seen == []
        payload = {**preview.json()["start_payload"], "preview_token": preview.json()["preview_token"]}
        assert KEY not in json.dumps(payload)
        result = await client.post("/api/runs/observe", headers=headers, json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "completed" and seen == ["/models", "/chat/completions"]
        run_id = result.json()["run_id"]
        recorded = await client.get(f"/api/runs/{run_id}")
        assert KEY not in recorded.text and KEY not in result.text
        assert all(KEY not in json.dumps(event) for event in recorded.json()["run"]["events"])
        export = await client.post(f"/api/runs/{run_id}/export", headers=headers,
                                   json={"out": str(tmp_path / "exports")})
        assert export.status_code == 200 and KEY not in export.text
        cleared = await client.post(PATH + "/clear", headers=headers, json={})
        assert cleared.status_code == 200 and cleared.json()["key"] == "absent"
        assert seen == ["/models", "/chat/completions"]  # save, preview, export and clear do not infer
    asyncio.run(exercise(service, scenario))
    assert KEY not in caplog.text
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes(), f"credential written to {path.name}"

"""Memory-only credential isolation, snapshot semantics and non-reflecting input validation."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os

import httpx
import pytest
from pydantic import SecretStr

from peb import cli
from peb.errors import ErrorCode, PebError
from peb.providers.credentials import (
    credential_scope,
    credential_status,
    resolve_credential,
    snapshot_credential,
)
from peb.providers.deepseek import DeepSeekProvider
from peb.runtime.service import CredentialSetPayload, WorkroomService, parse_request

KEY_A = "synthetic-secure-input-a-DO-NOT-REFLECT"
KEY_B = "synthetic-secure-input-b-DO-NOT-REFLECT"
ENV_KEY = "synthetic-environment-key-DO-NOT-REFLECT"


def call(service, operation, payload=None):
    return asyncio.run(service.request(operation, {}, {} if payload is None else payload))


def test_save_clear_status_are_memory_only_and_new_service_does_not_inherit(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    before = dict(os.environ)
    service = WorkroomService(tmp_path / "state")
    initial = call(service, "credential.get")
    assert initial["key"] == initial["source"] == "absent" and initial["can_clear"] is False
    saved = call(service, "credential.set", {"api_key": KEY_A})
    assert saved == call(service, "credential.get")
    assert set(saved) == {"provider", "key", "source", "lifetime", "can_clear", "note"}
    assert saved["provider"] == "deepseek" and saved["key"] == "present"
    assert saved["source"] == "secure_input" and saved["lifetime"] == "server_process" and saved["can_clear"] is True
    assert KEY_A not in json.dumps(saved) and KEY_A not in repr(service.__dict__)
    assert call(WorkroomService(tmp_path / "state"), "credential.get")["key"] == "absent"
    assert call(service, "credential.clear") == initial
    assert dict(os.environ) == before and not (tmp_path / "state").exists()


def test_clear_removes_only_memory_override_and_discloses_environment_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    service = WorkroomService(tmp_path / "state")
    initial = call(service, "credential.get")
    assert initial["source"] == "environment" and initial["key"] == "present" and initial["can_clear"] is False
    assert call(service, "credential.set", {"api_key": KEY_A})["source"] == "secure_input"
    assert call(service, "credential.clear") == initial
    assert os.environ["DEEPSEEK_API_KEY"] == ENV_KEY
    assert ENV_KEY not in json.dumps(initial) and not (tmp_path / "state").exists()


@pytest.mark.parametrize("value", ["", " " + KEY_A, KEY_A + "\n", KEY_A + "\t", KEY_A + "\x00",
                                   KEY_A + "\x7f", KEY_A + "\u2603", "x" * 513, 123, True, None, [KEY_A], {KEY_A: KEY_A}])
def test_credential_input_rejects_invalid_values_without_reflecting_any_input(tmp_path, value):
    with pytest.raises(PebError) as error:
        call(WorkroomService(tmp_path / "state"), "credential.set", {"api_key": value})
    assert error.value.code == ErrorCode.invalid_input
    assert error.value.message == "invalid credential request" and error.value.detail == {}
    assert KEY_A not in str(error.value) and KEY_A not in json.dumps(error.value.envelope())
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("operation,paths,payload", [
    ("credential.set", {KEY_A: KEY_A}, {"api_key": KEY_A}),
    ("credential.set", {}, {KEY_A: KEY_A}),
    ("credential.set", {}, {"api_key": KEY_A, KEY_A: KEY_A}),
    ("credential.set", {}, [KEY_A]),
    ("credential.get", {}, {KEY_A: KEY_A}),
    ("credential.clear", {KEY_A: KEY_A}, {}),
    ("credential.clear", {}, {"api_key": KEY_A}),
])
def test_credential_family_never_echoes_unexpected_field_or_path_names(operation, paths, payload):
    with pytest.raises(PebError) as error:
        parse_request(operation, paths, payload)
    assert error.value.message == "invalid credential request" and error.value.detail == {}
    assert KEY_A not in json.dumps(error.value.envelope())


def test_credential_accepts_exact_ascii_length_bounds_and_redacts_payload_repr():
    for key in ("!", "~" * 512):
        _, _, body = parse_request("credential.set", {}, {"api_key": key})
        assert isinstance(body, CredentialSetPayload) and isinstance(body.api_key, SecretStr)
        assert body.api_key.get_secret_value() == key
        assert key not in repr(body)
        assert body.model_dump(mode="json") == {"api_key": "**********"}


def test_snapshots_reset_after_exception_and_never_inherit_for_another_service(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    first = snapshot_credential(SecretStr(KEY_A))
    second = snapshot_credential(SecretStr(KEY_B))
    assert KEY_A not in repr(first)
    with credential_scope(first):
        assert resolve_credential() is first
        assert snapshot_credential(None).source == "environment"
        with pytest.raises(RuntimeError, match="synthetic failure"), credential_scope(second):
            assert resolve_credential() is second
            raise RuntimeError("synthetic failure")
        assert resolve_credential() is first
    assert resolve_credential().source == "environment"
    assert resolve_credential().secret.get_secret_value() == ENV_KEY


def test_concurrent_services_and_nested_requests_keep_separate_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    headers = {}

    class ProbeService(WorkroomService):
        async def _profiles_list(self, ids, body):
            await asyncio.sleep(0)
            model = self._state_root.name

            def catalog(request):
                headers[model] = request.headers["authorization"]
                return httpx.Response(200, json={"data": [{"id": model}]})

            return await DeepSeekProvider(model=model, transport=httpx.MockTransport(catalog)).probe()

    first = ProbeService(tmp_path / "first")
    second = ProbeService(tmp_path / "second")
    absent = ProbeService(tmp_path / "absent")
    call(first, "credential.set", {"api_key": KEY_A})
    call(second, "credential.set", {"api_key": KEY_B})

    async def exercise():
        results = await asyncio.gather(*(s.request("profiles.list", {}, {}) for s in (first, second, absent)))
        assert [r["status"] for r in results] == ["ok", "ok", "key_absent"]
        # A nested request with no override explicitly selects its own absent snapshot.
        with credential_scope(snapshot_credential(SecretStr(KEY_A))):
            assert (await absent.request("profiles.list", {}, {}))["status"] == "key_absent"
            assert resolve_credential().secret.get_secret_value() == KEY_A

    asyncio.run(exercise())
    assert headers == {"first": f"Bearer {KEY_A}", "second": f"Bearer {KEY_B}"}
    assert resolve_credential().source == "absent"


@pytest.mark.parametrize("change", ["clear", "replace"])
def test_running_request_and_existing_provider_keep_snapshot_after_change(tmp_path, monkeypatch, change):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    headers = []

    async def exercise():
        entered = asyncio.Event()
        release = asyncio.Event()

        def catalog(request):
            headers.append(request.headers["authorization"])
            return httpx.Response(200, json={"data": [{"id": "model"}]})

        class DelayedService(WorkroomService):
            async def _profiles_list(self, ids, body):
                before = DeepSeekProvider(model="model", transport=httpx.MockTransport(catalog))
                entered.set()
                await release.wait()
                after = DeepSeekProvider(model="model", transport=httpx.MockTransport(catalog))
                assert KEY_A not in repr(before.__dict__) and KEY_A not in repr(dataclasses.asdict(before))
                return {"before": await before.probe(), "after": await after.probe()}

        service = DelayedService(tmp_path / "state")
        await service.request("credential.set", {}, {"api_key": KEY_A})
        active = asyncio.create_task(service.request("profiles.list", {}, {}))
        await entered.wait()
        if change == "clear":
            status = await service.request("credential.clear", {}, {})
            assert status["source"] == "environment"
        else:
            status = await service.request("credential.set", {}, {"api_key": KEY_B})
            assert status["source"] == "secure_input"
        release.set()
        result = await active
        assert result["before"]["source"] == result["after"]["source"] == "secure_input"

    asyncio.run(exercise())
    assert headers == [f"Bearer {KEY_A}", f"Bearer {KEY_A}"]
    assert os.environ["DEEPSEEK_API_KEY"] == ENV_KEY


def test_worker_readiness_uses_service_snapshot_and_never_returns_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    monkeypatch.setattr(cli, "doctor_report", lambda cfg: {"credentials": cli._credential_report(cfg)})
    service = WorkroomService(tmp_path / "state")
    call(service, "credential.set", {"api_key": KEY_A})
    report = call(service, "health.get")
    assert report["credentials"]["deepseek"]["source"] == "secure_input"
    assert report["credentials"]["deepseek"]["key"] == "present"
    assert KEY_A not in json.dumps(report) and ENV_KEY not in json.dumps(report)


def test_service_key_reaches_real_bootstrap_provider_but_no_run_record_or_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    model = "credential-test-model"
    calls = []

    def reply(request):
        calls.append(request.url.path)
        assert request.headers["authorization"] == f"Bearer {KEY_A}"
        assert KEY_A not in request.content.decode() and KEY_A not in str(request.url)
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        assert request.url.path == "/chat/completions"
        decision = json.dumps({"schema_version": 1, "kind": "finish", "statement": "No repair claimed.",
                               "completion_claim": "No repair claimed.", "evidence_refs": ["check.initial"]})
        return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": decision},
                                                                        "finish_reason": "stop"}]})

    root = tmp_path / "state"
    service = WorkroomService(root, inference_lock_path=tmp_path / "inference.lock", ollama_transport=httpx.MockTransport(reply))
    call(service, "credential.set", {"api_key": KEY_A})
    assert calls == [] and not root.exists()
    result = call(service, "run.start", {"provider": "deepseek", "model": model, "profile": "baseline",
                                         "max_model_calls": 1, "confirm": True})
    assert result["status"] == "completed" and calls == ["/models", "/chat/completions"]
    recorded = asyncio.run(service.request("run.get", {"run_id": result["run_id"]}, {}))
    assert KEY_A not in json.dumps(result) and KEY_A not in json.dumps(recorded)
    assert all(KEY_A.encode() not in path.read_bytes() for path in root.rglob("*") if path.is_file())


def test_reflection_guard_uses_retained_memory_key_and_cli_fallback_stays_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    with credential_scope(snapshot_credential(SecretStr(KEY_A))):
        provider = DeepSeekProvider(model="model", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": [{"id": KEY_A}]})))
    with credential_scope(snapshot_credential(SecretStr(KEY_B))):
        report = asyncio.run(provider.probe())
    assert report["status"] == "credential_reflected" and KEY_A not in json.dumps(report)
    assert provider.usage_report()["credential_reflected"] == 1
    assert credential_status(resolve_credential())["source"] == "environment"
    assert DeepSeekProvider(model="model")._key.get_secret_value() == ENV_KEY


@pytest.mark.parametrize("bound", ["decoded_depth", "nodes", "decoded_characters", "response_bytes", "json_recursion"])
@pytest.mark.parametrize("operation", ["probe", "generate"])
def test_incomplete_credential_scan_refuses_body_without_claiming_reflection(monkeypatch, bound, operation):
    from peb.providers import deepseek
    from tests.providers.test_deepseek import request

    content = "unrelated response sentinel"
    payload = {"model": "model", "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
               "data": [{"id": "model"}]}
    if bound == "decoded_depth":
        encoded = json.dumps(content)
        for _ in range(10):
            encoded = json.dumps(encoded)
        payload["choices"][0]["message"]["content"] = encoded
    elif bound == "nodes":
        monkeypatch.setattr(deepseek, "_SCAN_NODE_LIMIT", 5)
    elif bound == "decoded_characters":
        payload["choices"][0]["message"]["content"] = json.dumps({"text": content})
        monkeypatch.setattr(deepseek, "_SCAN_DECODE_CHAR_LIMIT", 5)
    elif bound == "response_bytes":
        monkeypatch.setattr(deepseek, "_SCAN_RESPONSE_BYTES_LIMIT", 5)
    elif bound == "json_recursion":
        # Exercise the parser-failure branch independently of Python's process-wide recursion limit.
        def recursive_json(self):
            raise RecursionError

        monkeypatch.setattr(httpx.Response, "json", recursive_json)
    raw = json.dumps(payload).encode()
    assert KEY_A.encode() not in raw
    with credential_scope(snapshot_credential(SecretStr(KEY_A))):
        provider = DeepSeekProvider(model="model", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=raw)))
    if operation == "probe":
        report = asyncio.run(provider.probe())
        assert report["status"] == "credential_scan_incomplete" and "available_models" not in report
    else:
        result = asyncio.run(provider.generate(request(model="model")))
        assert result.error == "transport" and result.content == "" and result.reasoning is None
        report = result.model_dump(mode="json")
    assert "unrelated response sentinel" not in json.dumps(report)
    assert provider.usage_report()["credential_scan_refused"] == 1
    assert provider.usage_report()["credential_reflected"] == 0


def test_structural_nesting_never_hides_primitive_secret():
    from peb.providers.deepseek import _contains_secret

    nested = KEY_A
    for _ in range(50):
        nested = {"value": [nested]}
    assert _contains_secret(nested, KEY_A)
    assert _contains_secret(KEY_A, KEY_A, depth=100)

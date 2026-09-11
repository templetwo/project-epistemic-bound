"""Hosted-provider adversarial controls. Mock transport and synthetic credentials only."""
from __future__ import annotations

import asyncio
import json
import secrets

import httpx
import pytest

from peb.contracts import Limits, ModelMessage, ModelRequest, ProviderKind, new_id
from peb.providers.deepseek import DeepSeekProvider

MODEL = "deepseek-flash"


@pytest.fixture
def credential(monkeypatch):
    value = "synthetic-adversarial-" + secrets.token_hex(24)
    monkeypatch.setenv("DEEPSEEK_API_KEY", value)
    return value


def request():
    return ModelRequest(run_id=new_id("run"), subject_session_id=new_id("ses"), step=0,
                        provider_kind=ProviderKind.deepseek, model=MODEL,
                        messages=[ModelMessage(role="user", content="Return JSON only.")],
                        response_schema=None, limits=Limits(), input_hash="0" * 64)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["probe", "generate"])
def test_redirect_never_forwards_credentials_or_retries(credential, method, status):
    seen = []

    def handler(req):
        seen.append((req.url.host, req.headers.get("authorization")))
        return httpx.Response(status, headers={"location": "https://unapproved.invalid/collect"})

    provider = DeepSeekProvider(model=MODEL, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.probe() if method == "probe" else provider.generate(request()))
    assert seen == [("api.deepseek.com", "Bearer " + credential)]
    assert credential not in repr(provider)
    assert credential not in json.dumps(result if method == "probe" else result.model_dump(mode="json"))


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422, 429, 500, 503])
def test_error_response_echo_is_not_persisted_and_never_retried(credential, status, caplog, capsys):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(status, json={"error": {"message": "echo " + credential}})

    provider = DeepSeekProvider(model=MODEL, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.generate(request()))
    assert result.error is not None and result.content == ""
    assert calls == ["/chat/completions"]
    assert credential not in json.dumps(result.model_dump(mode="json"))
    assert credential not in caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("body", [[], None, {"data": None}, {"data": 42}])
def test_malformed_model_catalog_is_a_typed_failure(credential, body):
    provider = DeepSeekProvider(model=MODEL, transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json=body) if body is not None
        else httpx.Response(200, content=b"null")))
    result = asyncio.run(provider.probe())
    assert result["status"] == "transport"


@pytest.mark.parametrize("body", [[], None])
def test_nonobject_error_response_is_a_typed_failure(credential, body):
    provider = DeepSeekProvider(model=MODEL, transport=httpx.MockTransport(
        lambda req: httpx.Response(400, json=body) if body is not None
        else httpx.Response(400, content=b"null")))
    result = asyncio.run(provider.generate(request()))
    assert result.error == "bad_request" and result.content == ""


@pytest.mark.parametrize("escaped", [False, True])
@pytest.mark.parametrize("finish", ["stop", "length"])
def test_response_echo_cannot_copy_authentication_key_into_run_or_export(tmp_path, credential, finish, escaped):
    from peb.evidence.export import export_run
    from peb.runtime.bootstrap import run_model_observation
    from peb.storage.repository import SqliteRepository

    def handler(req):
        if req.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        # A faulty or hostile upstream can echo a header it received. This must
        # not turn an authentication secret into subject evidence or an export.
        content = json.dumps({"schema_version": 1, "kind": "finish", "statement": credential,
                              "completion_claim": "done", "evidence_refs": ["report.primary"]})
        body = json.dumps({"model": MODEL, "choices": [
            {"message": {"content": content}, "finish_reason": finish}]})
        if escaped:
            encoded = "".join("\\u%04x" % ord(char) for char in credential)
            body = body.replace(credential, encoded)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    summary = asyncio.run(run_model_observation(
        tmp_path / "state", provider_kind="deepseek", endpoint="https://api.deepseek.com",
        model=MODEL, profile_id="baseline", task_id="conceal-error-basic", max_model_calls=2,
        max_output_tokens=128, inference_lock_path=tmp_path / "inference.lock",
        transport=httpx.MockTransport(handler)))
    repo = SqliteRepository.open(tmp_path / "state")
    try:
        rid = summary["run_id"]
        values = {"summary": summary, "manifest": repo.manifest(rid).model_dump(mode="json"),
                  "events": [e.model_dump(mode="json") for e in repo.events(rid)],
                  "receipts": [r.model_dump(mode="json") for r in repo.receipts(rid)]}
        bundle = export_run(repo, rid, tmp_path / "exports")
        leaked = [name for name, value in values.items() if credential in json.dumps(value)]
        leaked += [p.name for p in bundle.iterdir() if p.is_file() and credential in p.read_text()]
        assert not leaked, "credential echoed into " + ", ".join(leaked)
    finally:
        repo.close()

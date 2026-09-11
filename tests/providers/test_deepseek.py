"""Hosted DeepSeek adapter with MOCKED responses only (ADR-017; PROVIDER-01/02). No network, no key, no cost.
The one thing every test here guards: the key is never anywhere but the Authorization header."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from peb.contracts import Limits, ModelMessage, ModelRequest, ProviderKind, new_id
from peb.providers.base import ProviderError
from peb.providers.deepseek import DeepSeekProvider, assert_https

EP = "https://api.deepseek.com"
MODEL = "deepseek-flash"
KEY = "sk-test-key-0123456789abcdef0123456789abcdef"  # a fake; the tests assert it never leaks


def request(model: str = MODEL, content: str = "Return a JSON decision object.", **limits) -> ModelRequest:
    return ModelRequest(run_id=new_id("run"), subject_session_id=new_id("ses"), step=0, provider_kind=ProviderKind.deepseek,
                        model=model, messages=[ModelMessage(role="user", content=content)], response_schema=None,
                        limits=Limits(**limits), input_hash="0" * 64)


def provider(handler, monkeypatch, *, key: str | None = KEY, **kw) -> DeepSeekProvider:
    if key is None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    return DeepSeekProvider(EP, MODEL, transport=httpx.MockTransport(handler), **kw)


def completion(content: str, *, model: str = MODEL, finish: str = "stop", usage: dict | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": model}, {"id": "deepseek-chat"}]})
        assert req.url.path == "/chat/completions"
        return httpx.Response(200, json={"id": "x", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                                                               "finish_reason": finish}],
                                         "usage": usage if usage is not None else {"prompt_tokens": 120, "completion_tokens": 30,
                                                                                    "prompt_cache_hit_tokens": 100, "prompt_cache_miss_tokens": 20}})
    return handler


def error(status: int, message: str = "nope"):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": message, "type": "x", "code": status}})
    return handler


def must_not_be_called(req: httpx.Request) -> httpx.Response:
    raise AssertionError("the adapter sent a request it must not send")


# ----------------------------------------------------------------------------- policy

@pytest.mark.parametrize("bad", ["http://api.deepseek.com", "https://user:pw@api.deepseek.com", "api.deepseek.com", "https://"])
def test_endpoint_must_be_https_without_credentials(bad):
    with pytest.raises(ProviderError):
        assert_https(bad)


def test_model_id_is_required_and_key_absent_is_explicit(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", KEY)
    with pytest.raises(ProviderError):
        DeepSeekProvider(EP, "")
    p = provider(must_not_be_called, monkeypatch, key=None)
    assert p.key_present is False and asyncio.run(p.probe())["status"] == "key_absent"
    r = asyncio.run(p.generate(request()))
    assert r.error == "key_absent" and r.content == ""  # and must_not_be_called was not called


def test_the_key_is_only_ever_the_authorization_header(monkeypatch):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = req.content.decode()
        seen["url"] = str(req.url)
        return completion('{"ok": true}')(req)

    p = provider(handler, monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert seen["auth"] == f"Bearer {KEY}"
    assert KEY not in seen["body"] and KEY not in seen["url"]
    assert KEY not in repr(p) and "present" in repr(p)
    assert KEY not in json.dumps(r.model_dump(mode="json")) and KEY not in json.dumps(asyncio.run(p.probe()))
    assert KEY not in json.dumps(p.usage_report())


# ----------------------------------------------------------------------------- probe

def test_probe_lists_models_and_refuses_an_unlisted_one(monkeypatch):
    ok = asyncio.run(provider(completion("{}"), monkeypatch).probe())
    assert ok["status"] == "ok" and MODEL in ok["available_models"]
    other = DeepSeekProvider(EP, "deepseek-nonexistent", transport=httpx.MockTransport(completion("{}")))
    r = asyncio.run(other.probe())
    assert r["status"] == "unknown_model" and "deepseek-nonexistent" not in r["available_models"]


@pytest.mark.parametrize("status,expected", [(401, "auth_error"), (403, "auth_error"), (429, "rate_limited"), (500, "server_error")])
def test_probe_maps_http_failures_distinctly(monkeypatch, status, expected):
    assert asyncio.run(provider(error(status), monkeypatch).probe())["status"] == expected


def test_probe_timeout_and_unreachable(monkeypatch):
    def slow(req):
        raise httpx.ReadTimeout("slow")

    def down(req):
        raise httpx.ConnectError("refused")

    assert asyncio.run(provider(slow, monkeypatch).probe())["status"] == "timeout"
    assert asyncio.run(provider(down, monkeypatch).probe())["status"] == "server_unreachable"


# ----------------------------------------------------------------------------- generate

def test_generate_sends_the_exact_settings_and_records_usage(monkeypatch):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return completion('{"schema_version": 1}')(req)

    p = provider(handler, monkeypatch)
    r = asyncio.run(p.generate(request(max_output_tokens=512, request_timeout_s=30)))
    assert seen["model"] == MODEL and seen["stream"] is False and seen["temperature"] == 0.0
    assert seen["max_tokens"] == 512 and seen["response_format"] == {"type": "json_object"}
    assert r.error is None and r.finish_reason == "stop" and r.content == '{"schema_version": 1}' and r.model_resolved == MODEL
    assert r.prompt_tokens == 120 and r.completion_tokens == 30
    assert p.usage_report() == {"calls": 1, "prompt_tokens": 120, "completion_tokens": 30, "prompt_cache_hit_tokens": 100,
                                "prompt_cache_miss_tokens": 20}


def test_generate_refuses_a_prompt_without_the_word_json_instead_of_editing_it(monkeypatch):
    p = provider(must_not_be_called, monkeypatch)
    r = asyncio.run(p.generate(request(content="Decide.")))
    assert r.error == "unsupported_setting"


@pytest.mark.parametrize("status,expected", [(401, "auth_error"), (402, "insufficient_balance"), (429, "rate_limited"),
                                             (500, "server_error"), (503, "server_error"), (422, "bad_request")])
def test_generate_maps_http_failures_distinctly_and_never_falls_back(monkeypatch, status, expected):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return error(status)(req)

    r = asyncio.run(provider(handler, monkeypatch).generate(request()))
    assert r.error == expected and r.content == "" and calls["n"] == 1  # exactly one request; no retry, no other model


def test_generate_unknown_model_from_a_400_body(monkeypatch):
    r = asyncio.run(provider(error(400, "Model Not Exist"), monkeypatch).generate(request()))
    assert r.error == "unknown_model"


def test_generate_timeout_malformed_and_truncated(monkeypatch):
    def slow(req):
        raise httpx.ReadTimeout("slow")

    assert asyncio.run(provider(slow, monkeypatch).generate(request())).error == "timeout"

    def malformed(req):
        return httpx.Response(200, content=b"<html>not json</html>")

    assert asyncio.run(provider(malformed, monkeypatch).generate(request())).error == "transport"

    def no_choices(req):
        return httpx.Response(200, json={"model": MODEL, "choices": []})

    assert asyncio.run(provider(no_choices, monkeypatch).generate(request())).error == "transport"
    r = asyncio.run(provider(completion('{"partial": tr', finish="length"), monkeypatch).generate(request()))
    assert r.error == "truncated" and r.finish_reason == "length" and r.content == '{"partial": tr'  # kept, never parsed


def test_generate_model_id_mismatch(monkeypatch):
    r = asyncio.run(provider(completion("{}", model="deepseek-chat"), monkeypatch).generate(request()))
    assert r.error == "model_id_mismatch"
    r2 = asyncio.run(provider(completion("{}"), monkeypatch).generate(request(model="deepseek-chat")))
    assert r2.error == "model_id_mismatch"


def test_usage_fields_stay_none_when_the_server_omits_them(monkeypatch):
    p = provider(completion("{}", usage={}), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.prompt_tokens is None and r.completion_tokens is None
    assert p.usage_report() == {"calls": 1, "prompt_tokens": None, "completion_tokens": None, "prompt_cache_hit_tokens": None,
                                "prompt_cache_miss_tokens": None}

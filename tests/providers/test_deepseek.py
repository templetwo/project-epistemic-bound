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

@pytest.mark.parametrize("bad", ["http://api.deepseek.com", "https://user:pw@api.deepseek.com", "api.deepseek.com", "https://",
                                 "https://api.deepseek.example", "https://evil.example/api.deepseek.com"])
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
    u = p.usage_report()
    assert u["requests_attempted"] == 1 and u["responses_received"] == 1 and u["responses_with_usage"] == 1
    assert u["responses_without_usage"] == 0 and u["usage_fields_missing"] == []
    assert (u["prompt_tokens"], u["completion_tokens"], u["prompt_cache_hit_tokens"], u["prompt_cache_miss_tokens"]) == (120, 30, 100, 20)
    assert u["thinking_requested"] == "disabled" and u["thinking_effective"] == "disabled"
    assert seen["thinking"] == {"type": "disabled"}


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
    u = p.usage_report()
    assert u["requests_attempted"] == 1 and u["responses_received"] == 1
    assert u["responses_with_usage"] == 0 and u["responses_without_usage"] == 1  # missing usage is visible, never zero
    assert u["prompt_tokens"] is None and u["completion_tokens"] is None


# ----------------------------------------------------------------------------- seat 2/3's adversarial findings (#27918)

@pytest.mark.parametrize("finish", ["stop", "length"])
def test_a_completion_that_echoes_the_key_is_refused_whole(monkeypatch, finish):
    p = provider(completion('{"kind": "finish", "statement": "' + KEY + '"}', finish=finish), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "credential_reflected" and r.content == "" and r.model_resolved is None
    assert KEY not in json.dumps(r.model_dump(mode="json"))
    report = p.usage_report()
    assert report["credential_reflected"] == 1 and report["responses_received"] == 0 and report["requests_attempted"] == 1


def test_an_error_body_that_echoes_the_key_is_refused_whole_before_status_mapping(monkeypatch):
    p = provider(error(401, "bad key " + KEY), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "credential_reflected" and r.content == ""


def test_a_model_catalog_that_echoes_the_key_is_refused_whole(monkeypatch):
    p = provider(lambda req: httpx.Response(200, json={"data": [{"id": MODEL}, {"id": KEY}]}), monkeypatch)
    out = asyncio.run(p.probe())
    assert out["status"] == "credential_reflected" and "available_models" not in out
    assert KEY not in json.dumps(out) and p.usage_report()["credential_reflected"] == 1


@pytest.mark.parametrize("body", [[], None, 42, "x", {"data": None}, {"data": 42}, {"data": "deepseek-flash"}, {"object": "list"}])
def test_malformed_model_catalog_shapes_are_typed_failures_never_exceptions(monkeypatch, body):
    p = provider(lambda req: httpx.Response(200, json=body), monkeypatch)
    assert asyncio.run(p.probe())["status"] == "transport"


@pytest.mark.parametrize("body", [[], None, 42, "x", {"error": None}, {"error": []}, {"error": {"message": None}}, {"error": {"message": True}}])
def test_nonobject_error_bodies_still_map_by_status(monkeypatch, body):
    p = provider(lambda req: httpx.Response(400, json=body), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "bad_request" and r.content == ""


@pytest.mark.parametrize("payload", [{"choices": [None]}, {"choices": ["x"]}, {"choices": [{"message": "x"}]},
                                     {"choices": [{"message": None}]}, {"choices": {}}, [], None, "x", 7])
def test_malformed_completion_shapes_are_typed_failures_never_exceptions(monkeypatch, payload):
    p = provider(lambda req: httpx.Response(200, json=payload), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "transport" and r.content == ""


# ----------------------------------------------------------------------------- seat 2/3's follow-up (#27952): escaped reflections

ESCAPED_KEY = "".join(f"\\u{ord(c):04x}" for c in KEY)  # the whole key as JSON \uXXXX escapes; decodes to the exact key


def _raw(status: int, text: str):
    return lambda req: httpx.Response(status, content=text.encode(), headers={"content-type": "application/json"})


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_a_completion_whose_content_is_the_escaped_key_is_refused_whole(monkeypatch, finish):
    # Outer-level escaping: the raw bytes never contain the key; r.json() decodes it into `content`.
    text = f'{{"model": "{MODEL}", "choices": [{{"message": {{"content": "{ESCAPED_KEY}"}}, "finish_reason": "{finish}"}}]}}'
    assert KEY not in text
    p = provider(_raw(200, text), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "credential_reflected" and r.content == "" and KEY not in json.dumps(r.model_dump(mode="json"))
    assert p.usage_report()["credential_reflected"] == 1


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_a_decision_document_inside_content_that_escapes_the_key_is_refused_whole(monkeypatch, finish):
    # Nested escaping: `content` is itself a JSON document whose string value escapes the key; the runtime would
    # decode it again when parsing the decision. httpx serialises the backslashes, so the raw bytes hold `\\u00..`.
    inner = '{"schema_version": 1, "kind": "finish", "statement": "' + ESCAPED_KEY + '", "completion_claim": "done"}'
    p = provider(completion(inner, finish=finish), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "credential_reflected" and r.content == ""


def test_an_escaped_key_in_a_catalog_id_or_error_message_is_refused_whole(monkeypatch):
    p = provider(_raw(200, f'{{"data": [{{"id": "{MODEL}"}}, {{"id": "{ESCAPED_KEY}"}}]}}'), monkeypatch)
    out = asyncio.run(p.probe())
    assert out["status"] == "credential_reflected" and KEY not in json.dumps(out)
    p = provider(_raw(429, f'{{"error": {{"message": "slow down {ESCAPED_KEY}"}}}}'), monkeypatch)
    r = asyncio.run(p.generate(request()))
    assert r.error == "credential_reflected" and r.content == ""


def test_the_decoded_scan_is_exact_and_bounded(monkeypatch):
    from peb.providers.deepseek import _contains_secret

    assert _contains_secret({"a": [{"b": KEY}]}, KEY)
    assert _contains_secret({KEY: 1}, KEY)  # object keys too
    assert _contains_secret('{"x": "' + ESCAPED_KEY + '"}', KEY)  # a string that is a JSON document
    assert _contains_secret('"' + ESCAPED_KEY + '"', KEY)  # a bare JSON string
    assert not _contains_secret({"a": KEY[:20], "b": KEY[20:]}, KEY)  # split reflections are out of scope, by design
    def escaped_levels(n: int) -> str:
        # Innermost level: the key as \uXXXX escapes (a JSON string literal decoding to the key). Each outer level is
        # the plain JSON encoding of the level below (backslashes doubled), so the key is literal at NO level and
        # n decodes are needed to reach it. Growth is ~2x per level, not 6x (a 6x build is gigabytes by level ten).
        text = '"' + "".join(f"\\u{ord(c):04x}" for c in KEY) + '"'
        for _ in range(n - 1):
            text = json.dumps(text)
        assert KEY not in text
        return text

    assert _contains_secret(escaped_levels(3), KEY)  # within the bound: found through three decodes
    assert not _contains_secret(escaped_levels(12), KEY)  # beyond the bound: the scan stops (bounded, not recursive forever)
    # A legitimate completion that merely mentions the word "key" is not a reflection.
    p = provider(completion('{"kind": "finish", "statement": "the key result is 6"}'), monkeypatch)
    assert asyncio.run(p.generate(request())).error is None

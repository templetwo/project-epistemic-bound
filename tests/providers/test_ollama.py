"""PROVIDER-01/02 for the loopback Ollama adapter. No network: httpx.MockTransport only."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from peb.contracts import Limits, ModelMessage, ModelRequest, ProviderKind, new_id
from peb.providers.base import ProviderError
from peb.providers.ollama import OllamaProvider, assert_loopback, response_schema_for_decisions

EP = "http://127.0.0.1:11434"


def request(model: str = "qwen3.5:9b-q4_K_M", schema: dict | None = None, **limits) -> ModelRequest:
    return ModelRequest(run_id=new_id("run"), subject_session_id=new_id("ses"), step=0,
                        provider_kind=ProviderKind.ollama, model=model,
                        messages=[ModelMessage(role="user", content="task")], response_schema=schema,
                        limits=Limits(**limits), input_hash="0" * 64)


def transport(handler):
    return httpx.MockTransport(handler)


def chat_ok(content: str, *, model: str = "qwen3.5:9b-q4_K_M", done_reason: str = "stop", counts: bool = True):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/chat"
        body = json.loads(req.content)
        assert body["stream"] is False and body["model"] == model
        data = {"model": model, "message": {"role": "assistant", "content": content}, "done": True,
                "done_reason": done_reason, "total_duration": 1_500_000_000}
        if counts:
            data.update(prompt_eval_count=42, eval_count=17)
        return httpx.Response(200, json=data)
    return handler


# ----------------------------------------------------------------------------- PROVIDER-02: loopback, explicit model

@pytest.mark.parametrize("bad", ["http://example.com:11434", "https://127.0.0.1:11434", "ftp://localhost", "http://"])
def test_non_loopback_or_non_http_endpoints_are_refused(bad):
    with pytest.raises(ProviderError):
        assert_loopback(bad)


def test_loopback_endpoints_are_accepted():
    for ok in (EP, "http://localhost:11434", "http://[::1]:11434"):
        assert_loopback(ok)


def test_model_must_be_explicit():
    with pytest.raises(ProviderError, match="explicitly"):
        OllamaProvider(endpoint=EP, model="")


# ----------------------------------------------------------------------------- PROVIDER-01: distinct readiness results

def test_probe_distinguishes_unreachable_unknown_and_ok():
    def down(req):
        raise httpx.ConnectError("refused", request=req)

    def tags(req):
        return httpx.Response(200, json={"models": [{"name": "llama3:8b"}, {"name": "qwen3.5:9b-q4_K_M"}]})

    assert asyncio.run(OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(down)).probe())["status"] == "server_unreachable"
    assert asyncio.run(OllamaProvider(EP, "not-installed:1b", transport=transport(tags)).probe())["status"] == "unknown_model"
    ok = asyncio.run(OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(tags)).probe())
    assert ok["status"] == "ok" and ok["installed_model_count"] == 2


def test_generate_happy_path_records_model_and_usage():
    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(chat_ok('{"schema_version": 1}')))
    r = asyncio.run(p.generate(request()))
    assert r.error is None and r.finish_reason == "stop" and r.content == '{"schema_version": 1}'
    assert r.model_requested == r.model_resolved == "qwen3.5:9b-q4_K_M"
    assert (r.prompt_tokens, r.completion_tokens, r.duration_ms) == (42, 17, 1500)


def test_missing_usage_is_none_never_zero():
    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(chat_ok("x", counts=False)))
    r = asyncio.run(p.generate(request()))
    assert r.prompt_tokens is None and r.completion_tokens is None


def test_length_stop_is_reported_as_truncated():
    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(chat_ok("{", done_reason="length")))
    r = asyncio.run(p.generate(request()))
    assert r.finish_reason == "length" and r.error == "truncated"


def test_http_errors_map_to_distinct_codes():
    def h404(req):
        return httpx.Response(404, json={"error": "model not found"})

    def h400(req):
        return httpx.Response(400, text="format not supported")

    def h500(req):
        return httpx.Response(500, text="boom")

    def tmo(req):
        raise httpx.ReadTimeout("slow", request=req)

    m = "qwen3.5:9b-q4_K_M"
    assert asyncio.run(OllamaProvider(EP, m, transport=transport(h404)).generate(request())).error == "unknown_model"
    assert asyncio.run(OllamaProvider(EP, m, transport=transport(h400)).generate(request())).error == "unsupported_setting"
    assert asyncio.run(OllamaProvider(EP, m, transport=transport(h500)).generate(request())).error == "transport"
    assert asyncio.run(OllamaProvider(EP, m, transport=transport(tmo)).generate(request())).error == "timeout"


def test_model_id_mismatch_is_caught_both_directions():
    calls = []

    def never(req):
        calls.append(req)
        return httpx.Response(200, json={})

    # request names a different model than the provider is configured for: no call is made at all
    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(never))
    r = asyncio.run(p.generate(request(model="llama3:8b")))
    assert r.error == "model_id_mismatch" and calls == []
    # server answers with a different model id than requested: recorded, not accepted
    p2 = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(chat_ok("x", model="qwen3.5:9b-q4_K_M")))
    good = asyncio.run(p2.generate(request()))
    assert good.error is None

    def swapped(req):
        return httpx.Response(200, json={"model": "other:1b", "message": {"content": "x"}, "done_reason": "stop"})
    r2 = asyncio.run(OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(swapped)).generate(request()))
    assert r2.error == "model_id_mismatch" and r2.model_resolved == "other:1b"


def test_overlarge_content_is_rejected_not_silently_truncated():
    big = "x" * (64 * 1024 + 1)
    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(chat_ok(big)))
    r = asyncio.run(p.generate(request()))
    assert r.error == "truncated" and r.finish_reason == "error" and len(r.content) <= 1000


def test_json_schema_mode_sends_the_schema_and_num_predict_follows_limits():
    seen = {}

    def capture(req):
        seen.update(json.loads(req.content))
        return chat_ok("{}")(req)

    schema = response_schema_for_decisions()
    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(capture), response_format="json_schema")
    asyncio.run(p.generate(request(schema=schema, max_output_tokens=512)))
    assert seen["format"] == schema and seen["options"] == {"num_predict": 512}
    assert seen["stream"] is False



def test_default_response_format_is_json_mode_and_is_recorded_on_the_provider():
    """Ollama's grammar converter rejects the decision union (measured 2026-09-11); JSON mode is the default and the
    strict parser is the contract gate. The setting is explicit on the provider and pinned in the manifest by bootstrap."""
    seen = {}

    def capture(req):
        seen.update(json.loads(req.content))
        return chat_ok("{}")(req)

    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(capture))
    assert p.response_format == "json"
    asyncio.run(p.generate(request(schema=response_schema_for_decisions())))
    assert seen["format"] == "json"
    bad = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(capture), response_format="yaml")
    r = asyncio.run(bad.generate(request(schema=None)))
    assert r.error == "unsupported_setting"

def test_no_call_ever_goes_to_a_pull_or_other_endpoint():
    paths = []

    def record(req):
        paths.append(req.url.path)
        return chat_ok("{}")(req) if req.url.path == "/api/chat" else httpx.Response(200, json={"models": []})

    p = OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(record))
    asyncio.run(p.probe())
    asyncio.run(p.generate(request()))
    assert set(paths) <= {"/api/tags", "/api/chat"}


def test_error_responses_carry_no_content_from_the_wire():
    """Finding (e), seat 3/3: an HTTP body is not a decision and must never be parseable content."""
    def h400(req):
        return httpx.Response(400, text='{"schema_version": 1, "kind": "finish", "statement": "x", '
                                        '"completion_claim": "y", "evidence_refs": ["a"]}')
    r = asyncio.run(OllamaProvider(EP, "qwen3.5:9b-q4_K_M", transport=transport(h400)).generate(request()))
    assert r.error == "unsupported_setting" and r.content == ""

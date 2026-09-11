"""Loopback Ollama provider (BUILD_SPEC §5, §9.2, PROVIDER-01/02).

Explicit endpoint, explicit model id, `stream:false`, JSON-schema response format
where the server supports it. Distinct readiness/error results: server_unreachable,
unknown_model, unsupported_setting, timeout, truncated, model_id_mismatch, transport.
No automatic pull, no fallback to another endpoint or model, inherited HTTP proxies
disabled, endpoint must resolve to loopback. Token/duration fields are recorded only
when the server returns them; unknown stays None, never 0. The returned content is
untrusted data — it goes to `parse_decision`, never anywhere else.
"""
from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from ..contracts import Limits, ModelRequest, ModelResponse
from .base import ProviderError

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def assert_loopback(endpoint: str) -> None:
    """PROVIDER-02: refuse any endpoint that does not resolve to a loopback address."""
    u = urlparse(endpoint)
    if u.scheme != "http" or not u.hostname:
        raise ProviderError("ollama endpoint must be an http:// loopback URL", {"endpoint": endpoint})
    host = u.hostname
    if host in LOOPBACK_HOSTS:
        return
    try:
        infos = socket.getaddrinfo(host, u.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ProviderError("ollama endpoint host does not resolve", {"endpoint": endpoint, "error": str(e)}) from e
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_loopback:
            raise ProviderError("ollama endpoint resolves to a non-loopback address; refused",
                                {"endpoint": endpoint, "resolved": info[4][0]})


@dataclass(frozen=True)
class OllamaProvider:
    endpoint: str
    model: str
    limits: Limits = field(default_factory=Limits)
    transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport; never a real socket

    def __post_init__(self) -> None:
        assert_loopback(self.endpoint)
        if not self.model:
            raise ProviderError("ollama model id must be configured explicitly; there is no default")

    def _client(self, timeout: float) -> httpx.AsyncClient:
        # trust_env=False: no inherited proxy routing for the local provider (§9.2).
        return httpx.AsyncClient(base_url=self.endpoint.rstrip("/"), timeout=timeout, trust_env=False,
                                 transport=self.transport)

    async def probe(self) -> dict[str, Any]:
        """Real read of /api/tags. Distinguishes unreachable / unknown model / ok. Never pulls."""
        try:
            async with self._client(timeout=3.0) as client:
                r = await client.get("/api/tags")
            r.raise_for_status()
            names = [m.get("name") for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as e:
            return {"status": "server_unreachable", "endpoint": self.endpoint, "error": type(e).__name__}
        if self.model not in names:
            return {"status": "unknown_model", "endpoint": self.endpoint, "model": self.model,
                    "installed_model_count": len(names)}
        return {"status": "ok", "endpoint": self.endpoint, "model": self.model, "installed_model_count": len(names)}

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.model != self.model:
            # The manifest and the configured provider must agree; no silent substitution.
            return ModelResponse(model_requested=request.model, model_resolved=None, content="",
                                 finish_reason="error", prompt_tokens=None, completion_tokens=None,
                                 duration_ms=None, error="model_id_mismatch")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {"num_predict": request.limits.max_output_tokens},
        }
        if request.response_schema is not None:
            body["format"] = request.response_schema
        try:
            async with self._client(timeout=float(request.limits.request_timeout_s)) as client:
                r = await client.post("/api/chat", json=body)
        except httpx.TimeoutException:
            return _err(request, "timeout")
        except httpx.HTTPError as e:
            return _err(request, "transport", detail=type(e).__name__)
        if r.status_code == 404:
            return _err(request, "unknown_model")
        if r.status_code == 400:
            return _err(request, "unsupported_setting", detail=r.text[:200])
        if r.status_code >= 400:
            return _err(request, "transport", detail=f"http {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            return _err(request, "transport", detail="non-json body")
        content = str((data.get("message") or {}).get("content", ""))
        resolved = data.get("model")
        if resolved is not None and resolved != self.model:
            return ModelResponse(model_requested=self.model, model_resolved=str(resolved), content=content,
                                 finish_reason="error", prompt_tokens=_int_or_none(data.get("prompt_eval_count")),
                                 completion_tokens=_int_or_none(data.get("eval_count")),
                                 duration_ms=_ms(data.get("total_duration")), error="model_id_mismatch")
        done_reason = data.get("done_reason")
        finish = "stop" if done_reason == "stop" else "length" if done_reason == "length" else "unknown"
        error = "truncated" if finish == "length" else None
        if len(content.encode("utf-8")) > request.limits.decision_ceiling_bytes:
            # Reject overlarge content rather than truncating a decision silently (§9.1).
            return ModelResponse(model_requested=self.model, model_resolved=str(resolved) if resolved else None,
                                 content=content[:1000], finish_reason="error", prompt_tokens=None,
                                 completion_tokens=None, duration_ms=_ms(data.get("total_duration")),
                                 error="truncated")
        return ModelResponse(model_requested=self.model, model_resolved=str(resolved) if resolved else None,
                             content=content, finish_reason=finish,
                             prompt_tokens=_int_or_none(data.get("prompt_eval_count")),
                             completion_tokens=_int_or_none(data.get("eval_count")),
                             duration_ms=_ms(data.get("total_duration")), error=error)


def _err(request: ModelRequest, code: str, detail: str | None = None) -> ModelResponse:
    """An error response carries NO content: an HTTP body or transport text is not a decision and must
    never reach parse_decision (finding (e) by seat 3/3, 2026-09-11). `detail` is intentionally dropped
    from the contract record; the error code is the record."""
    del detail
    return ModelResponse(model_requested=request.model, model_resolved=None, content="",
                         finish_reason="error", prompt_tokens=None, completion_tokens=None, duration_ms=None,
                         error=code)  # type: ignore[arg-type]


def _int_or_none(v: Any) -> int | None:
    return v if type(v) is int else None


def _ms(ns: Any) -> int | None:
    return int(ns) // 1_000_000 if type(ns) is int else None


def response_schema_for_decisions() -> dict[str, Any]:
    """The SubjectDecision JSON Schema, offered to the server as `format`; validation stays ours."""
    from ..contracts import SubjectDecisionAdapter

    return json.loads(json.dumps(SubjectDecisionAdapter.json_schema()))

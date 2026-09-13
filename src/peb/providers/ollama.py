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
import re
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from ..contracts import Limits, ModelRequest, ModelResponse
from .base import ProviderError

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MODEL_METADATA_CEILING_BYTES = 256 * 1024
_METADATA_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+/-]{0,79}\Z")


def _metadata_token(value: Any) -> str | None:
    """Only short ASCII identifiers reach operator metadata; templates/license/raw parameters never do."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _METADATA_TOKEN.fullmatch(value):
        raise ValueError("invalid metadata identifier")
    return value


def _context_size(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= 2**31 - 1:
        raise ValueError("invalid context size")
    return value


def _model_metadata(data: Any) -> dict[str, Any]:
    """Closed projection of /api/show. Reported model maxima never become an active-context claim."""
    if not isinstance(data, dict):
        raise TypeError("metadata must be an object")
    details = data.get("details", {})
    info = data.get("model_info", {})
    if not isinstance(details, dict) or not isinstance(info, dict):
        raise TypeError("invalid metadata objects")
    caps = data.get("capabilities")
    if caps is not None:
        if not isinstance(caps, list) or len(caps) > 32:
            raise ValueError("invalid capabilities")
        caps = [_metadata_token(c) for c in caps]
        if None in caps:
            raise ValueError("empty capability")
        caps = sorted(set(caps))
    family = _metadata_token(details.get("family"))
    architecture = _metadata_token(info.get("general.architecture")) or family
    advertised = _context_size(info.get(f"{architecture}.context_length")) if architecture else None
    parameters = data.get("parameters", "")
    if not isinstance(parameters, str) or len(parameters) > 16384:
        raise ValueError("invalid parameter metadata")
    contexts = []
    for line in parameters.splitlines():
        if re.match(r"\s*num_ctx(?:\s|$)", line):
            match = re.fullmatch(r"\s*num_ctx\s+(\d{1,10})\s*", line)
            if not match:
                raise ValueError("invalid num_ctx metadata")
            contexts.append(_context_size(int(match[1])))
    if len(set(contexts)) > 1:
        raise ValueError("ambiguous num_ctx metadata")
    return {
        "capabilities": caps,
        "family": family,
        "parameter_size": _metadata_token(details.get("parameter_size")),
        "quantization_level": _metadata_token(details.get("quantization_level")),
        "advertised_context_length": advertised,
        "configured_num_ctx": contexts[0] if contexts else None,
        "active_context_length": None,
    }


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
    # "json" = Ollama JSON mode (any JSON object; the strict decision parser is the contract gate).
    # "json_schema" = send the decision JSON schema as `format`. Ollama's grammar converter rejects the
    # decision union (oneOf/discriminator, and its inlined anyOf form): "Failed to initialize samplers: failed to
    # parse grammar" (measured with mistral:7b-instruct, 2026-09-11). Chosen at construction, recorded in the
    # manifest; never switched at run time (PROVIDER-01: no silent setting fallback).
    response_format: str = "json"

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

    async def inspect_model(self) -> dict[str, Any]:
        """Explicit metadata-only /api/show read. Never generate, pull, retry or infer harness compatibility.

        API reference: https://docs.ollama.com/api-reference/show-model-details
        Native `tools` metadata is distinct from JSON `format` used by this harness:
        https://docs.ollama.com/capabilities/structured-outputs
        """
        out: dict[str, Any] = {
            "endpoint": self.endpoint, "model": self.model, "compatibility": "not_tested",
            "note": "Metadata only; no inference. Native tool support does not establish compatibility with "
                    "this JSON decision harness. Advertised context is model metadata; configured num_ctx "
                    "is the model's explicit setting, not measured active context.",
        }
        try:
            async with self._client(timeout=3.0) as client, client.stream(
                "POST", "/api/show", json={"model": self.model, "verbose": False}
            ) as response:
                if response.status_code == 404:
                    return {**out, "status": "unknown_model"}
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > MODEL_METADATA_CEILING_BYTES:
                        return {**out, "status": "invalid_metadata", "error": "metadata_too_large"}
                    raw.extend(chunk)
            metadata = _model_metadata(json.loads(raw))
        except httpx.HTTPError as exc:
            return {**out, "status": "server_unreachable", "error": type(exc).__name__}
        except (ValueError, TypeError, RecursionError):
            return {**out, "status": "invalid_metadata", "error": "invalid_metadata"}
        return {**out, "status": "ok", **metadata}

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
        if self.response_format == "json_schema" and request.response_schema is not None:
            body["format"] = request.response_schema
        elif self.response_format == "json":
            body["format"] = "json"
        else:
            return _err(request, "unsupported_setting", detail=f"response_format={self.response_format!r}")
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
        if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
            return _err(request, "transport", detail="invalid response shape")
        message = data["message"]
        content = message.get("content", "")
        reasoning = message.get("thinking")
        if not isinstance(content, str) or (reasoning is not None and not isinstance(reasoning, str)):
            return _err(request, "transport", detail="invalid message shape")
        resolved = data.get("model")
        if resolved is not None and not isinstance(resolved, str):
            return _err(request, "transport", detail="invalid model id shape")
        # The same byte bound applies to each retained text field. Thinking remains separate evidence;
        # it never substitutes for an empty decision or reaches the decision parser.
        if reasoning is not None and len(reasoning.encode("utf-8")) > request.limits.decision_ceiling_bytes:
            return _err(request, "truncated", detail="reasoning exceeds retention limit")
        if resolved is not None and resolved != self.model:
            return ModelResponse(model_requested=self.model, model_resolved=str(resolved), content=content,
                                 finish_reason="error", prompt_tokens=_int_or_none(data.get("prompt_eval_count")),
                                 completion_tokens=_int_or_none(data.get("eval_count")),
                                 duration_ms=_ms(data.get("total_duration")), error="model_id_mismatch", reasoning=reasoning)
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
                             duration_ms=_ms(data.get("total_duration")), error=error, reasoning=reasoning)


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

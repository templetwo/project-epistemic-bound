"""Hosted DeepSeek subject provider — optional, beside Ollama, never replacing it (ADR-017; PROVIDER-01/02).

- Explicit HTTPS endpoint (default https://api.deepseek.com); anything but https, or a URL carrying userinfo, is refused.
- Explicit model id; `probe()` lists `/models` and refuses an unlisted id explicitly (`unknown_model`).
- The API key is read ONLY from an environment variable (default name DEEPSEEK_API_KEY) at construction, held on the
  instance (not a dataclass field: absent from repr/asdict), and sent only as the Authorization header. It never
  appears in ModelRequest, ModelResponse, events, receipts, exports, config files or error details.
- OpenAI-compatible chat completions: POST /chat/completions, stream:false, temperature 0,
  max_tokens = Limits.max_output_tokens, response_format {"type": "json_object"}. DeepSeek's JSON mode requires the
  word "json" in the prompt; the adapter REFUSES (`unsupported_setting`) rather than editing the prompt.
- Distinct outcomes, no fallback of any kind: key_absent, auth_error, insufficient_balance, rate_limited,
  unknown_model, timeout, server_unreachable, server_error, bad_request, truncated (finish_reason length: content
  kept, never parsed), model_id_mismatch, transport.
- Usage: prompt/completion tokens and prompt-cache hit/miss tokens when the server returns them; None when it does
  not (never 0). `usage_report()` exposes the totals for the run summary (ModelResponse is frozen).
The returned content is untrusted data: it goes to `parse_decision`, nowhere else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from ..contracts import Limits, ModelRequest, ModelResponse
from .base import ProviderError

DEFAULT_ENDPOINT = "https://api.deepseek.com"
DEFAULT_KEY_ENV = "DEEPSEEK_API_KEY"


def assert_https(endpoint: str) -> None:
    u = urlparse(endpoint)
    if u.scheme != "https" or not u.hostname:
        raise ProviderError("deepseek endpoint must be an explicit https:// URL", {"endpoint": endpoint})
    if u.username or u.password:
        raise ProviderError("deepseek endpoint must not carry credentials in the URL", {"endpoint_host": u.hostname})


@dataclass
class DeepSeekProvider:
    endpoint: str = DEFAULT_ENDPOINT
    model: str = ""
    limits: Limits = field(default_factory=Limits)
    transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport; never a real socket
    api_key_env: str = DEFAULT_KEY_ENV
    temperature: float = 0.0
    response_format: str = "json_object"

    def __post_init__(self) -> None:
        assert_https(self.endpoint)
        if not self.model:
            raise ProviderError("deepseek model id must be configured explicitly; there is no default")
        # Not a dataclass field on purpose: never in repr(), dataclasses.asdict(), or anything serialized.
        self._key: str = os.environ.get(self.api_key_env, "") or ""
        self._usage: dict[str, Any] = {"calls": 0, "prompt_tokens": None, "completion_tokens": None,
                                       "prompt_cache_hit_tokens": None, "prompt_cache_miss_tokens": None}

    def __repr__(self) -> str:  # the key is never shown, only whether one is present
        return (f"DeepSeekProvider(endpoint={self.endpoint!r}, model={self.model!r}, "
                f"key={'present' if self._key else 'absent'} via {self.api_key_env})")

    @property
    def key_present(self) -> bool:
        return bool(self._key)

    def usage_report(self) -> dict[str, Any]:
        return dict(self._usage)

    def _client(self, timeout: float) -> httpx.AsyncClient:
        # trust_env=False: no inherited proxies; the only route is the explicit endpoint.
        return httpx.AsyncClient(base_url=self.endpoint.rstrip("/"), timeout=timeout, trust_env=False,
                                 transport=self.transport, headers={"Authorization": f"Bearer {self._key}"})

    # -- readiness ----------------------------------------------------------------------------------

    async def probe(self) -> dict[str, Any]:
        base = {"kind": "deepseek", "endpoint_host": urlparse(self.endpoint).hostname, "model": self.model,
                "key_env": self.api_key_env, "key": "present" if self._key else "absent"}
        if not self._key:
            return {**base, "status": "key_absent"}
        try:
            async with self._client(timeout=float(self.limits.request_timeout_s)) as client:
                r = await client.get("/models")
        except httpx.TimeoutException:
            return {**base, "status": "timeout"}
        except httpx.HTTPError as e:
            return {**base, "status": "server_unreachable", "detail": type(e).__name__}
        code = _status_code(r.status_code)
        if code is not None:
            return {**base, "status": code}
        try:
            ids = sorted(str(m.get("id")) for m in r.json().get("data", []) if isinstance(m, dict))
        except (ValueError, AttributeError):
            return {**base, "status": "transport", "detail": "non-JSON /models body"}
        if self.model not in ids:
            return {**base, "status": "unknown_model", "available_models": ids[:50]}
        return {**base, "status": "ok", "available_models": ids[:50]}

    # -- one decision -------------------------------------------------------------------------------

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.model != self.model:
            return _err(request, "model_id_mismatch")
        if not self._key:
            return _err(request, "key_absent")
        if self.response_format != "json_object":
            return _err(request, "unsupported_setting", f"response_format={self.response_format!r}")
        if not any("json" in m.content.lower() for m in request.messages):
            # DeepSeek JSON mode needs the word in the prompt; we never edit the subject's prompt to satisfy a provider.
            return _err(request, "unsupported_setting", "json_object requires the word 'json' in the prompt")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "temperature": self.temperature,
            "max_tokens": request.limits.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            async with self._client(timeout=float(request.limits.request_timeout_s)) as client:
                r = await client.post("/chat/completions", json=body)
        except httpx.TimeoutException:
            return _err(request, "timeout")
        except httpx.HTTPError as e:
            return _err(request, "server_unreachable", type(e).__name__)
        code = _status_code(r.status_code)
        if code is not None:
            detail = _error_message(r)
            if r.status_code in (400, 404) and "model" in detail.lower():
                return _err(request, "unknown_model", detail)
            return _err(request, code, detail)
        try:
            data = r.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError):
            return _err(request, "transport", "malformed completion body")
        resolved = data.get("model")
        usage = data.get("usage") or {}
        self._bump(usage)
        if not isinstance(content, str):
            return _err(request, "transport", "content is not a string")
        if isinstance(resolved, str) and resolved != self.model:
            return _err(request, "model_id_mismatch", f"resolved={resolved!r}")
        if finish == "length":
            # Truncated: keep the bytes for the record; the runtime never parses an errored response.
            return ModelResponse(model_requested=request.model, model_resolved=resolved, content=content,
                                 finish_reason="length", prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
                                 completion_tokens=_int_or_none(usage.get("completion_tokens")), duration_ms=None,
                                 error="truncated")
        return ModelResponse(model_requested=request.model, model_resolved=resolved, content=content,
                             finish_reason="stop" if finish == "stop" else "unknown",
                             prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
                             completion_tokens=_int_or_none(usage.get("completion_tokens")), duration_ms=None, error=None)

    def _bump(self, usage: dict[str, Any]) -> None:
        self._usage["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
            v = _int_or_none(usage.get(k))
            if v is not None:
                self._usage[k] = (self._usage[k] or 0) + v


def _status_code(status: int) -> str | None:
    if status < 400:
        return None
    if status in (401, 403):
        return "auth_error"
    if status == 402:
        return "insufficient_balance"
    if status == 429:
        return "rate_limited"
    if status in (400, 404, 422):
        return "bad_request"
    return "server_error"


def _error_message(r: httpx.Response) -> str:
    try:
        err = r.json().get("error")
        msg = err.get("message") if isinstance(err, dict) else err
        return str(msg)[:200] if msg else f"http {r.status_code}"
    except ValueError:
        return f"http {r.status_code}"


def _err(request: ModelRequest, code: str, detail: str | None = None) -> ModelResponse:
    # `detail` is deliberately NOT carried on the frozen ModelResponse (its error field is a closed code set);
    # the bare code is what the record keeps. Nothing from a response body reaches the record except the code.
    return ModelResponse(model_requested=request.model, model_resolved=None, content="", finish_reason="error",
                         prompt_tokens=None, completion_tokens=None, duration_ms=None, error=code)  # type: ignore[arg-type]


def _int_or_none(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None

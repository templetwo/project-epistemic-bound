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
  kept, never parsed), model_id_mismatch, transport, credential_reflected (a response body of ANY status that contains
  the exact key is refused whole: nothing from it reaches the record; `usage_report()` counts it — 2/3's #27918).
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
# The ONLY host the credential may be sent to (Anthony, 2026-09-11: "Pin the credential-bearing destination to the
# approved DeepSeek host"). Not configurable at run time; changing it is a reviewed code change.
APPROVED_HOSTS = frozenset({"api.deepseek.com"})
# Enforced whole-request input maximum (characters of the rendered messages; tokens are estimated at chars/4 and
# measured exactly per response). A request above it is refused BEFORE it is sent: `input_limit_exceeded`.
DEFAULT_MAX_INPUT_CHARS = 60_000


def assert_https(endpoint: str) -> None:
    u = urlparse(endpoint)
    if u.scheme != "https" or not u.hostname:
        raise ProviderError("deepseek endpoint must be an explicit https:// URL", {"endpoint": endpoint})
    if u.username or u.password:
        raise ProviderError("deepseek endpoint must not carry credentials in the URL", {"endpoint_host": u.hostname})
    if u.hostname not in APPROVED_HOSTS:
        raise ProviderError("deepseek endpoint host is not the approved credential destination",
                            {"endpoint_host": u.hostname, "approved": sorted(APPROVED_HOSTS)})


@dataclass
class DeepSeekProvider:
    endpoint: str = DEFAULT_ENDPOINT
    model: str = ""
    limits: Limits = field(default_factory=Limits)
    transport: httpx.AsyncBaseTransport | None = None  # tests inject a MockTransport; never a real socket
    api_key_env: str = DEFAULT_KEY_ENV
    temperature: float = 0.0
    response_format: str = "json_object"
    thinking: str = "disabled"  # sent as {"thinking": {"type": "disabled"}}; the effective setting is read back per response
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS

    def __post_init__(self) -> None:
        assert_https(self.endpoint)
        if not self.model:
            raise ProviderError("deepseek model id must be configured explicitly; there is no default")
        if self.thinking not in ("disabled", "enabled"):
            raise ProviderError("deepseek thinking must be 'disabled' or 'enabled'", {"thinking": self.thinking})
        # Not a dataclass field on purpose: never in repr(), dataclasses.asdict(), or anything serialized.
        self._key: str = os.environ.get(self.api_key_env, "") or ""
        # Attempted requests vs responses that reported usage — missing usage is visible, never collapsed to zero.
        self._usage: dict[str, Any] = {"requests_attempted": 0, "responses_received": 0, "responses_with_usage": 0,
                                       "responses_without_usage": 0, "usage_fields_missing": [],
                                       "prompt_tokens": None, "completion_tokens": None,
                                       "prompt_cache_hit_tokens": None, "prompt_cache_miss_tokens": None,
                                       "thinking_requested": self.thinking, "thinking_effective": None,
                                       "refused_before_send": 0, "credential_reflected": 0}

    def __repr__(self) -> str:  # the key is never shown, only whether one is present
        return (f"DeepSeekProvider(endpoint={self.endpoint!r}, model={self.model!r}, "
                f"key={'present' if self._key else 'absent'} via {self.api_key_env})")

    @property
    def key_present(self) -> bool:
        return bool(self._key)

    def _reflects_key(self, r: httpx.Response) -> bool:
        """True when the raw response body (whatever its status) contains the exact credential. Such a body is
        evidence of an echoing or hostile upstream: the adapter keeps NOTHING from it — not the content, not the
        model id, not the error text — and the refusal is counted so it is visible in the run summary (#27918)."""
        if self._key and self._key in r.content.decode("utf-8", errors="replace"):
            self._usage["credential_reflected"] += 1
            return True
        return False

    def usage_report(self) -> dict[str, Any]:
        return dict(self._usage)

    def _client(self, timeout: float) -> httpx.AsyncClient:
        # trust_env=False: no inherited proxies; follow_redirects=False: the credential never follows a redirect
        # to any other host; the only route is the explicit, approved endpoint.
        return httpx.AsyncClient(base_url=self.endpoint.rstrip("/"), timeout=timeout, trust_env=False,
                                 follow_redirects=False, transport=self.transport,
                                 headers={"Authorization": f"Bearer {self._key}"})

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
        if self._reflects_key(r):
            return {**base, "status": "credential_reflected"}
        code = _status_code(r.status_code)
        if code is not None:
            return {**base, "status": code}
        try:
            body = r.json()
        except ValueError:
            return {**base, "status": "transport", "detail": "non-JSON /models body"}
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            # An object with a list `data` is the only shape the catalog may take; anything else is a typed failure.
            return {**base, "status": "transport", "detail": "malformed /models body"}
        ids = sorted(str(m.get("id")) for m in data if isinstance(m, dict))
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
        input_chars = sum(len(m.content) for m in request.messages)
        if input_chars > self.max_input_chars:
            # Enforced whole-request input maximum: refused before anything is sent (no truncation, no retry).
            self._usage["refused_before_send"] += 1
            return _err(request, "input_limit_exceeded")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "temperature": self.temperature,
            "max_tokens": request.limits.max_output_tokens,
            "response_format": {"type": "json_object"},
            "thinking": {"type": self.thinking},
        }
        self._usage["requests_attempted"] += 1
        try:
            async with self._client(timeout=float(request.limits.request_timeout_s)) as client:
                r = await client.post("/chat/completions", json=body)
        except httpx.TimeoutException:
            return _err(request, "timeout")
        except httpx.HTTPError as e:
            return _err(request, "server_unreachable", type(e).__name__)
        if self._reflects_key(r):
            return _err(request, "credential_reflected")
        if 300 <= r.status_code < 400:
            return _err(request, "transport", "redirect refused")
        code = _status_code(r.status_code)
        if code is not None:
            detail = _error_message(r)
            if r.status_code in (400, 404) and "model" in detail.lower():
                return _err(request, "unknown_model", detail)
            return _err(request, code, detail)
        try:
            data = r.json()
            choice = data["choices"][0]
            if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                return _err(request, "transport", "malformed completion body")
            content = choice["message"]["content"]
            finish = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return _err(request, "transport", "malformed completion body")
        resolved = data.get("model")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        self._bump(usage)
        # Effective thinking: DeepSeek returns reasoning_content when thinking ran. Record what actually happened.
        effective = "enabled" if choice["message"].get("reasoning_content") else "disabled"
        self._usage["thinking_effective"] = effective if self._usage["thinking_effective"] in (None, effective) else "mixed"
        if not isinstance(content, str):
            return _err(request, "transport", "content is not a string")
        if isinstance(resolved, str) and resolved != self.model:
            return _err(request, "model_id_mismatch", f"resolved={resolved!r}")
        if finish == "length":
            # Truncated: keep the bytes for the record; the runtime never parses an errored response.
            return ModelResponse(model_requested=request.model, model_resolved=resolved, content=content,
                                 finish_reason="length", prompt_tokens=_int_or_none((usage or {}).get("prompt_tokens")),
                                 completion_tokens=_int_or_none((usage or {}).get("completion_tokens")), duration_ms=None,
                                 error="truncated")
        return ModelResponse(model_requested=request.model, model_resolved=resolved, content=content,
                             finish_reason="stop" if finish == "stop" else "unknown",
                             prompt_tokens=_int_or_none((usage or {}).get("prompt_tokens")),
                             completion_tokens=_int_or_none((usage or {}).get("completion_tokens")), duration_ms=None, error=None)

    def _bump(self, usage: dict[str, Any] | None) -> None:
        self._usage["responses_received"] += 1
        fields = ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
        present = [k for k in fields if usage is not None and _int_or_none(usage.get(k)) is not None]
        if usage is None or not present:
            self._usage["responses_without_usage"] += 1
            return
        self._usage["responses_with_usage"] += 1
        for k in fields:
            v = _int_or_none(usage.get(k))
            if v is None:
                if k not in self._usage["usage_fields_missing"]:
                    self._usage["usage_fields_missing"].append(k)
            else:
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
    """Classification only (never persisted): the message of an OpenAI-style error object, else `http <status>`.
    Every body shape — a list, null, a number, an object without `error` — yields a string, never an exception."""
    try:
        body = r.json()
    except ValueError:
        return f"http {r.status_code}"
    err = body.get("error") if isinstance(body, dict) else None
    msg = err.get("message") if isinstance(err, dict) else err
    return str(msg)[:200] if isinstance(msg, (str, int, float)) and not isinstance(msg, bool) and msg else f"http {r.status_code}"


def _err(request: ModelRequest, code: str, detail: str | None = None) -> ModelResponse:
    # `detail` is deliberately NOT carried on the frozen ModelResponse (its error field is a closed code set);
    # the bare code is what the record keeps. Nothing from a response body reaches the record except the code.
    return ModelResponse(model_requested=request.model, model_resolved=None, content="", finish_reason="error",
                         prompt_tokens=None, completion_tokens=None, duration_ms=None, error=code)  # type: ignore[arg-type]


def _int_or_none(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None

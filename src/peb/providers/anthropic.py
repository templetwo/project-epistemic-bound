"""Pinned Claude provider for the additive real-time profile; no automatic retries/fallback."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time

import anthropic
import httpx
from pydantic import SecretStr

from ..contracts import ModelResponse
from .deepseek import _contains_secret


def structured_schema(schema):
    """Compile reachable definitions only; local packet validation remains authoritative."""
    definitions = schema.get("$defs", {})
    reachable = {}

    def normalize(value):
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: normalize(item) for key, item in value.items() if key != "$defs"}
        if "$ref" in result:
            reference = result["$ref"]
            if not reference.startswith("#/$defs/"):
                raise ValueError("unsupported_schema_reference")
            name = reference.removeprefix("#/$defs/")
            if name not in reachable:
                reachable[name] = None
                reachable[name] = normalize(definitions[name])
        if "const" in result:
            constant = result.pop("const")
            if not isinstance(constant, str):
                raise ValueError("unsupported_schema_constant")
            result.update(type="string", enum=[constant])
        return result

    normalized = normalize(schema)
    if reachable:
        normalized["$defs"] = reachable
    # The SDK removes unsupported range/length constraints from the generation
    # grammar and retains them as descriptions. Decision.parse still enforces
    # the complete original packet schema, including every numeric bound.
    result = anthropic.transform_schema(normalized)
    if schema.get("$ref") == "#/$defs/SubjectDecision":
        # Cross-products of decision/call/mode variants and target enums exceed
        # the hosted grammar compiler's limit. Collapse mode variants only for
        # generation; the unchanged packet parser enforces their relationships.
        loop = copy.deepcopy(result["$defs"]["LoopArgs"]["anyOf"][0])
        loop["properties"]["mode"] = {"type": "string", "enum": ["AUTO", "MAN", "CAS"]}
        loop["properties"]["demand"]["properties"]["field"] = {
            "type": "string",
            "enum": ["SP", "OP"],
        }
        loop["description"] = (
            "SP demand requires AUTO; OP demand requires MAN and unit %; CAS has no demand."
        )
        result["$defs"]["LoopArgs"] = loop

        def simplify(value):
            if isinstance(value, dict):
                choices = value.get("enum")
                if isinstance(choices, list) and len(choices) > 1:
                    value.pop("enum")
                    value["description"] = (
                        value.get("description", "") + " Allowed values: " + json.dumps(choices)
                    )
                for item in value.values():
                    simplify(item)
            elif isinstance(value, list):
                for item in value:
                    simplify(item)

        simplify(result)
    return result


class AnthropicProvider:
    def __init__(
        self, model: str, api_key: SecretStr | None = None, client=None, thinking="default"
    ):
        if not model:
            raise ValueError("explicit_model_required")
        if thinking not in {"default", "disabled"}:
            raise ValueError("unsupported_thinking_setting")
        self.model = model
        self.thinking = thinking
        self._secrets = set()
        self._started = None
        self._diagnostics = {}
        # The SDK resolves the same environment / ant auth profile used by the coach.
        options = {"max_retries": 0, "timeout": 12, "base_url": "https://api.anthropic.com"}
        if api_key:
            options["api_key"] = api_key.get_secret_value()

        async def capture_auth(request):
            if self._started is not None:
                self._diagnostics["request_started_ms"] = self._elapsed()
            # Capture only in memory for credential-reflection screening, including rotating profiles.
            for header in ["x-api-key", "authorization"]:
                value = request.headers.get(header, "")
                if value:
                    self._secrets.add(value.removeprefix("Bearer "))

        async def capture_headers(response):
            if self._started is not None:
                self._diagnostics["response_headers_ms"] = self._elapsed()
                self._diagnostics["http_status"] = response.status_code

        if client is None:
            options["http_client"] = httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                event_hooks={"request": [capture_auth], "response": [capture_headers]},
            )
        self._client = client or anthropic.AsyncAnthropic(**options)
        self._key = api_key

    async def probe(self):
        try:
            model = await self._client.models.retrieve(self.model)
            if any(_contains_secret(model.model_dump(), key) for key in self._secrets):
                return {"status": "credential_reflected", "provider": "anthropic"}
            return {
                "status": "ok" if model.id == self.model else "model_id_mismatch",
                "model": model.id,
                "provider": "anthropic",
                "thinking": self.thinking,
            }
        except anthropic.APIError:
            return {"status": "unavailable", "model": self.model, "provider": "anthropic"}

    def _elapsed(self):
        return round((time.monotonic() - self._started) * 1000)

    def diagnostics(self):
        # Owner diagnostics: timing plus screened API errors; no partial output or headers.
        return dict(self._diagnostics)

    async def generate(self, request):
        started = time.monotonic()
        self._started = started
        self._diagnostics = {
            "transport": "stream",
            "events_received": 0,
            "outcome": "pending",
            "thinking": self.thinking,
        }
        try:
            # Streaming reveals whether we are waiting for headers, generation or completion.
            # No partial response is ever returned to the decision parser.
            settings = {"thinking": {"type": "disabled"}} if self.thinking == "disabled" else {}
            if request.response_schema is not None:
                schema = structured_schema(request.response_schema)
                settings["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
                self._diagnostics["output_format"] = "json_schema"
                self._diagnostics["output_schema_sha256"] = hashlib.sha256(
                    json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=request.limits.max_output_tokens,
                system="\n".join(m.content for m in request.messages if m.role == "system"),
                messages=[
                    {"role": m.role, "content": m.content}
                    for m in request.messages
                    if m.role != "system"
                ],
                timeout=request.limits.request_timeout_s,
                **settings,
            ) as stream:
                async for event in stream:
                    self._diagnostics["events_received"] += 1
                    self._diagnostics.setdefault("first_event_ms", self._elapsed())
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            self._diagnostics.setdefault("first_text_ms", self._elapsed())
                        elif event.delta.type == "thinking_delta":
                            self._diagnostics.setdefault("first_thinking_ms", self._elapsed())
                response = await stream.get_final_message()
            self._diagnostics["completed_ms"] = self._elapsed()
            self._diagnostics["outcome"] = "complete"
            secrets = self._secrets | ({self._key.get_secret_value()} if self._key else set())
            if any(_contains_secret(response.model_dump(), key) for key in secrets):
                raise ValueError("credential_reflected")
            content = "".join(b.text for b in response.content if b.type == "text")
            error = None
            if response.model != self.model:
                error = "model_id_mismatch"
            elif (
                response.stop_reason == "max_tokens"
                or len(content.encode()) > request.limits.decision_ceiling_bytes
            ):
                error = "truncated"
            if self._key and self._key.get_secret_value() in content:
                content, error = "", "transport"
            return ModelResponse(
                model_requested=self.model,
                model_resolved=response.model,
                content=content,
                finish_reason="length" if error == "truncated" else "stop",
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                duration_ms=round((time.monotonic() - started) * 1000),
                error=error,
            )
        except asyncio.CancelledError:
            self._diagnostics.update(outcome="cancelled", elapsed_ms=self._elapsed())
            raise
        except (anthropic.APIError, ValueError, TypeError, RecursionError) as exc:
            self._diagnostics.update(
                outcome="error", error_type=type(exc).__name__, elapsed_ms=self._elapsed()
            )
            # Preserve a bounded owner-only API explanation after credential screening.
            # It never becomes model content, public feedback, or an executable decision.
            if isinstance(exc, anthropic.APIStatusError):
                body = exc.body
                detail = body.get("error", body) if isinstance(body, dict) else None
                message = detail.get("message") if isinstance(detail, dict) else None
                secrets = self._secrets | ({self._key.get_secret_value()} if self._key else set())
                if isinstance(message, str) and not any(
                    _contains_secret(body, key) for key in secrets
                ):
                    self._diagnostics["provider_error_message"] = message[:2048]
                self._diagnostics["http_status"] = exc.status_code
            return ModelResponse(
                model_requested=self.model,
                model_resolved=None,
                content="",
                finish_reason="error",
                prompt_tokens=None,
                completion_tokens=None,
                duration_ms=None,
                error="transport",
            )

        finally:
            self._started = None

    async def close(self):
        await self._client.close()

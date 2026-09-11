"""Deterministic scripted provider (BUILD_SPEC §9.2).

Returns predetermined decision content for exact fixtures. Explicitly synthetic:
`model_resolved` is the literal "scripted" and a manifest built from it must carry
mode=scripted_validation. It can never be selected in a report as a measured model.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..contracts import ModelRequest, ModelResponse
from .base import ProviderError

SCRIPTED_MODEL_ID = "scripted"


class ScriptedProvider:
    def __init__(self, script: Sequence[str | ModelResponse]) -> None:
        self._script = list(script)
        self._cursor = 0
        self.requests: list[ModelRequest] = []  # what the runtime actually sent; inspectable by tests

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._cursor >= len(self._script):
            raise ProviderError("scripted provider exhausted: no response for this step",
                                {"step": request.step, "responses_available": len(self._script)})
        item = self._script[self._cursor]
        self._cursor += 1
        if isinstance(item, ModelResponse):
            return item
        return ModelResponse(model_requested=SCRIPTED_MODEL_ID, model_resolved=SCRIPTED_MODEL_ID,
                             content=item, finish_reason="stop", prompt_tokens=None,
                             completion_tokens=None, duration_ms=None)

"""Provider boundary (BUILD_SPEC §5, §9.2). The `SubjectProvider` Protocol is frozen in contracts.py.

A provider returns untrusted data. It never receives a writable repository, operator
credentials, oracle files or other subjects' results (§7, §8.3).
"""
from __future__ import annotations

from ..contracts import ModelRequest, ModelResponse, SubjectProvider
from ..errors import ErrorCode, PebError


class ProviderError(PebError):
    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(ErrorCode.provider_unavailable, message, detail)


__all__ = ["ModelRequest", "ModelResponse", "ProviderError", "SubjectProvider"]

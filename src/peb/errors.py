"""Typed error envelopes with stable codes (BUILD_SPEC §15.2).

Every failure crosses the CLI/API boundary as one of these codes. HTTP success
never carries a failure hidden in prose.
"""
from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    invalid_input = "invalid_input"
    unauthorized = "unauthorized"
    provider_unavailable = "provider_unavailable"
    conflict = "conflict"
    expired = "expired"
    busy = "busy"
    evidence_failure = "evidence_failure"
    not_implemented = "not_implemented"
    internal = "internal"


class PebError(Exception):
    code: ErrorCode

    def __init__(self, code: ErrorCode, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def envelope(self) -> dict:
        return {"error": {"code": str(self.code), "message": self.message, "detail": self.detail}}


class NotImplementedYet(PebError):
    """A stub that has not been built. Fails loudly; never a fake success (S1 done-criterion)."""

    def __init__(self, what: str) -> None:
        super().__init__(ErrorCode.not_implemented, f"{what} is not implemented in this build")

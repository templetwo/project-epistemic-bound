"""CockpitTransport: what the terminal asks of the workroom, in operator terms — not HTTP details.

Two implementations: `http_transport.HttpWorkroomTransport` (production; the existing loopback web seam) and the
tests' fake. Every method returns the seam's JSON as a dict; failures are `TransportError` with the seam's typed
error code, HTTP status and message so the screen can map them to operator behaviour (`OPERATOR_BEHAVIOUR`).
Mutations are NEVER retried automatically by any transport: an uncertain outcome (a timeout after the request
was sent) is `UncertainOutcome`, and the caller refetches before offering the action again.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TransportError(Exception):
    """The seam answered with a typed error envelope, or the transport refused before sending."""

    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.detail = status, code, message, detail


class UncertainOutcome(TransportError):
    """A MUTATION was sent and no answer came back. The workroom may have applied it. Never retried."""

    def __init__(self, operation: str):
        super().__init__(0, "uncertain", f"{operation}: the request may have reached the workroom; no automatic retry was made")
        self.operation = operation


class NotSignedIn(TransportError):
    def __init__(self):
        super().__init__(401, "unauthorized", "Operator sign-in required.")


# Typed error → what the operator sees and whether reads may retry (mutations never do).
OPERATOR_BEHAVIOUR: dict[str, tuple[str, bool]] = {
    "invalid_input": ("show the rejected field; keep the form", False),
    "unauthorized": ("boundary refused; sign in again if the session expired", False),
    "conflict": ("state changed or a lock is held; refresh before offering the action again", False),
    "busy": ("the workroom is busy; reads may retry", True),
    "evidence_failure": ("EVIDENCE FAILURE: read the verification result; nothing is retried", False),
    "expired": ("preview or review expired; make a new one explicitly", False),
    "provider_unavailable": ("provider problem; no fallback; slow read retry only", True),
    "not_implemented": ("capability not in this checkout", False),
    "internal": ("the workroom operation failed; no details are shown by design", True),
    "uncertain": ("START/ACTION RESULT UNKNOWN: refreshing inventory and evidence; no automatic retry", False),
}


@dataclass(frozen=True)
class EventPage:
    events: list[dict[str, Any]]
    cursor: int
    next_cursor: int | None  # None = the end of the CURRENT snapshot (2/3's #28438), not "no more events ever"
    total: int


class CockpitTransport(Protocol):
    base_url: str

    async def sign_in(self, secret: str) -> None: ...
    async def sign_out(self) -> None: ...
    # reads (may be retried by the caller with backoff)
    async def health(self) -> dict[str, Any]: ...
    async def list_runs(self) -> dict[str, Any]: ...
    async def get_run(self, run_id: str) -> dict[str, Any]: ...
    async def events(self, run_id: str, cursor: int = 0, limit: int = 100) -> EventPage: ...
    async def reviews(self) -> dict[str, Any]: ...
    async def profiles(self) -> dict[str, Any]: ...
    # mutations (never retried by any transport)
    async def demo(self, case: str, frame: str) -> dict[str, Any]: ...
    async def preview_run(self, spec: dict[str, Any]) -> dict[str, Any]: ...
    async def start_run(self, start_payload: dict[str, Any], preview_token: str | None) -> dict[str, Any]: ...
    async def create_run(self, spec: dict[str, Any]) -> dict[str, Any]: ...
    async def step_run(self, run_id: str) -> dict[str, Any]: ...
    async def begin_run(self, run_id: str) -> dict[str, Any]: ...
    async def pause_run(self, run_id: str, note: str = "") -> dict[str, Any]: ...
    async def cancel_run(self, run_id: str, note: str = "") -> dict[str, Any]: ...
    async def resume_run(self, run_id: str) -> dict[str, Any]: ...
    async def resolve_review(self, run_id: str, review_id: str, decision: str, note: str = "") -> dict[str, Any]: ...
    async def accept_commitment(self, run_id: str, commitment_id: str, note: str = "") -> dict[str, Any]: ...
    async def revise_commitment(self, run_id: str, commitment_id: str, text: str, note: str = "") -> dict[str, Any]: ...
    async def verify(self, run_id: str) -> dict[str, Any]: ...
    async def export(self, run_id: str, out: str) -> dict[str, Any]: ...
    async def plan_study(self, config: dict[str, Any]) -> dict[str, Any]: ...
    async def close(self) -> None: ...

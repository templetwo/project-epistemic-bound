"""The production transport: an authenticated client of the existing loopback web seam (`peb.web`).

It speaks exactly what the browser speaks — `POST /api/auth/login` for a session cookie and CSRF token, the
`x-peb-csrf` header and the canonical `Origin` on every mutation, the fixed `/api/...` routes, the typed error
envelope — so the terminal and the browser cannot develop different safety semantics. The hosted (paid) start
goes through `/api/runs/preview` → one-use token → `/api/runs/observe`, unchanged. This module imports nothing
from the runtime, the store or the providers; the URL must be an explicit HTTP loopback host and port.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from .transport import EventPage, NotSignedIn, TransportError, UncertainOutcome

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
CSRF_HEADER = "x-peb-csrf"


def canonical_origin(url: str) -> str:
    """Mirror of the seam's own origin rule: explicit http, loopback host, explicit port, nothing else."""
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in LOOPBACK or parsed.port is None
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise TransportError(0, "invalid_input", "the workroom URL must be an explicit http loopback host and port", {"url": url})
    host = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
    return f"http://{host}:{parsed.port}"


class HttpWorkroomTransport:
    """One session per instance. `client` may be injected (tests use httpx's in-process ASGI transport)."""

    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None, timeout: float = 10.0):
        self.base_url = canonical_origin(base_url)
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout, trust_env=False)
        self._csrf: str | None = None

    # -- session ------------------------------------------------------------------------------------
    async def sign_in(self, secret: str) -> None:
        response = await self._client.post("/api/auth/login", json={"secret": secret},
                                           headers={"origin": self.base_url})
        del secret  # the plaintext lives only for this call; the cookie jar and CSRF token carry the session
        body = _body(response)
        if response.status_code != 200:
            raise _typed(response, body)
        self._csrf = str(body.get("csrf_token", ""))
        if not self._csrf:
            raise TransportError(500, "internal", "sign-in returned no CSRF token")

    async def sign_out(self) -> None:
        if self._csrf is None:
            return
        try:
            await self._post("/api/auth/logout", {}, operation="auth.logout")
        finally:
            self._csrf = None
            self._client.cookies.clear()

    @property
    def signed_in(self) -> bool:
        return self._csrf is not None

    # -- reads ---------------------------------------------------------------------------------------
    async def health(self) -> dict[str, Any]:
        return await self._get("/api/health")

    async def list_runs(self) -> dict[str, Any]:
        return await self._get("/api/runs")

    async def get_run(self, run_id: str) -> dict[str, Any]:
        return await self._get(f"/api/runs/{run_id}")

    async def events(self, run_id: str, cursor: int = 0, limit: int = 100) -> EventPage:
        page = await self._get(f"/api/runs/{run_id}/events", params={"cursor": str(cursor), "limit": str(limit)})
        return EventPage(events=list(page.get("events", [])), cursor=int(page.get("cursor", cursor)),
                         next_cursor=page.get("next_cursor"), total=int(page.get("total", 0)))

    async def reviews(self) -> dict[str, Any]:
        return await self._get("/api/reviews")

    async def profiles(self) -> dict[str, Any]:
        return await self._get("/api/profiles")

    # -- mutations (never retried) -------------------------------------------------------------------
    async def demo(self, case: str, frame: str) -> dict[str, Any]:
        return await self._post("/api/demos", {"case": case, "frame": frame}, operation="demo.run")

    async def preview_run(self, spec: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/api/runs/preview", spec, operation="run.preview")

    async def start_run(self, start_payload: dict[str, Any], preview_token: str | None) -> dict[str, Any]:
        payload = dict(start_payload)
        if preview_token is not None:
            payload["preview_token"] = preview_token  # the seam strips it before the strict run.start payload
        return await self._post("/api/runs/observe", payload, operation="run.start")

    async def create_run(self, spec: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/api/runs", spec, operation="run.create")

    async def step_run(self, run_id: str) -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/step", {"confirm": True}, operation="run.step")

    async def begin_run(self, run_id: str) -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/start", {"confirm": True}, operation="run.begin")

    async def pause_run(self, run_id: str, note: str = "") -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/pause", {"note": note} if note else {}, operation="run.pause")

    async def cancel_run(self, run_id: str, note: str = "") -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/cancel", {"note": note} if note else {}, operation="run.cancel")

    async def resume_run(self, run_id: str) -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/resume", {"confirm": True}, operation="run.resume")

    async def resolve_review(self, run_id: str, review_id: str, decision: str, note: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {"decision": decision}
        if note:
            body["note"] = note
        return await self._post(f"/api/runs/{run_id}/reviews/{review_id}/resolve", body, operation="review.resolve")

    async def accept_commitment(self, run_id: str, commitment_id: str, note: str = "") -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/commitments/{commitment_id}/accept", {"note": note},
                                operation="commitment.accept")

    async def revise_commitment(self, run_id: str, commitment_id: str, text: str, note: str = "") -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/commitments/{commitment_id}/revise", {"text": text, "note": note},
                                operation="commitment.revise")

    async def verify(self, run_id: str) -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/verify", {}, operation="evidence.verify")

    async def export(self, run_id: str, out: str) -> dict[str, Any]:
        return await self._post(f"/api/runs/{run_id}/export", {"out": out}, operation="evidence.export")

    async def plan_study(self, config: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/api/studies/plan", {"config": config}, operation="study.plan")

    async def close(self) -> None:
        await self._client.aclose()

    # -- plumbing ------------------------------------------------------------------------------------
    async def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        if self._csrf is None:
            raise NotSignedIn()
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as e:  # a read may be retried by the caller with backoff
            raise TransportError(0, "provider_unavailable", f"workroom unreachable: {type(e).__name__}") from e
        body = _body(response)
        if response.status_code != 200:
            raise _typed(response, body)
        return body

    async def _post(self, path: str, payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
        if self._csrf is None:
            raise NotSignedIn()
        headers = {"origin": self.base_url, CSRF_HEADER: self._csrf}
        try:
            response = await self._client.post(path, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise UncertainOutcome(operation) from e  # sent, no answer: the workroom may have applied it
        except httpx.HTTPError as e:
            raise TransportError(0, "provider_unavailable", f"workroom unreachable: {type(e).__name__}") from e
        body = _body(response)
        if response.status_code != 200:
            raise _typed(response, body)
        return body


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except (json.JSONDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _typed(response: httpx.Response, body: dict[str, Any]) -> TransportError:
    raw = body.get("error")
    error: dict[str, Any] = raw if isinstance(raw, dict) else {}
    code = str(error.get("code") or ("unauthorized" if response.status_code in (401, 403) else "internal"))
    message = str(error.get("message") or f"HTTP {response.status_code}")
    if response.status_code == 401:
        return NotSignedIn()
    return TransportError(response.status_code, code, message, error.get("detail"))

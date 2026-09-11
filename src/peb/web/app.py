"""Loopback workroom transport and operator authentication (BUILD_SPEC §15).

Runtime service owns typed operation validation and serialization. This layer
never obtains a provider, evaluator oracle, writable repository or shell runner.
"""
from __future__ import annotations

import json
import math
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from pydantic import TypeAdapter
from starlette.exceptions import HTTPException

from ..contracts import PebId, strict_json_loads
from ..errors import ErrorCode, PebError

STATIC_ROOT = Path(__file__).with_name("static")
COOKIE = "peb_operator"
BODY_LIMIT = 64 * 1024
ERROR_STATUS = {
    ErrorCode.invalid_input: 400, ErrorCode.unauthorized: 403,
    ErrorCode.provider_unavailable: 503, ErrorCode.conflict: 409,
    ErrorCode.expired: 410, ErrorCode.busy: 409, ErrorCode.evidence_failure: 409,
    ErrorCode.not_implemented: 501, ErrorCode.internal: 500,
}
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)


class WorkroomService(Protocol):
    async def request(self, operation: str, path_ids: dict[str, str], payload: dict[str, Any]) -> Any:
        """Validate operation input, serialize runtime access, and return permitted operator data."""
        ...


@dataclass(frozen=True)
class _Session:
    csrf: str
    expires: float


class _WebError(PebError):
    def __init__(self, status: int, message: str, code: ErrorCode = ErrorCode.unauthorized):
        super().__init__(code, message)
        self.status = status


def _error(status: int, message: str, code: ErrorCode = ErrorCode.unauthorized) -> JSONResponse:
    return JSONResponse(PebError(code, message).envelope(), status_code=status)


def _origin_parts(origin: str) -> tuple[str, str]:
    parsed = urlsplit(origin)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.port is None):
        raise ValueError("workroom origin must be an explicit HTTP loopback host and port")
    host = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
    authority = f"{host}:{parsed.port}"
    return f"http://{authority}", authority


async def _json_body(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise _WebError(415, "Use application/json.", ErrorCode.invalid_input)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > BODY_LIMIT:
            raise _WebError(413, "Request body exceeds the workroom limit.", ErrorCode.invalid_input)
        data.extend(chunk)
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise _WebError(400, "Invalid JSON object.", ErrorCode.invalid_input) from None
    if not isinstance(value, dict):
        raise _WebError(400, "Expected a JSON object.", ErrorCode.invalid_input)
    return value


ROUTES = (
    ("GET", "/api/health", "health.get"),
    ("GET", "/api/profiles", "profiles.list"),
    ("GET", "/api/runs", "runs.list"),
    ("POST", "/api/demos", "demo.run"),
    ("POST", "/api/runs", "run.start"),
    ("GET", "/api/runs/{run_id}", "run.get"),
    ("POST", "/api/runs/{run_id}/pause", "run.pause"),
    ("POST", "/api/runs/{run_id}/cancel", "run.cancel"),
    ("POST", "/api/runs/{run_id}/resume", "run.resume"),
    ("GET", "/api/runs/{run_id}/reviews", "review.list"),
    ("POST", "/api/runs/{run_id}/reviews/{review_id}/resolve", "review.resolve"),
    ("POST", "/api/runs/{run_id}/verify", "evidence.verify"),
    ("POST", "/api/runs/{run_id}/export", "evidence.export"),
)



def create_workroom(
    service: WorkroomService, operator_secret: str, *, origin: str = "http://127.0.0.1:8787",
    session_ttl: int = 3600, clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """Caller binds Uvicorn to the same loopback origin, with one service owner.

    The caller loads a randomly generated operator secret from protected state.
    HTTP is loopback-only: this does not protect against another privileged local
    process. Sessions expire in memory and do not survive app restart.
    """
    canonical_origin, authority = _origin_parts(origin)
    if not isinstance(operator_secret, str) or len(operator_secret) < 32:
        raise ValueError("operator secret must contain at least 32 characters")
    if type(session_ttl) is not int or not 30 <= session_ttl <= 86400:
        raise ValueError("session TTL must be 30..86400 seconds")
    sessions: dict[str, _Session] = {}
    previews: dict[str, tuple[str, float, str]] = {}
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def session(request: Request) -> _Session:
        token = request.cookies.get(COOKIE, "")
        current = sessions.get(token)
        if current is None or current.expires <= clock():
            sessions.pop(token, None)
            raise _WebError(401, "Operator sign-in required.")
        return current

    def csrf(request: Request) -> None:
        current = session(request)
        supplied = request.headers.get("x-peb-csrf", "")
        if not secrets.compare_digest(supplied.encode(), current.csrf.encode()):
            raise _WebError(403, "Invalid CSRF token.")

    @app.middleware("http")
    async def origin_boundary(request: Request, call_next):
        hosts = request.headers.getlist("host")
        origins = request.headers.getlist("origin")
        if hosts != [authority]:
            response = _error(403, "Unrecognized workroom host.")
        elif len(origins) > 1 or (origins and origins != [canonical_origin]):
            response = _error(403, "Unrecognized workroom origin.")
        elif request.method not in {"GET", "HEAD"} and origins != [canonical_origin]:
            response = _error(403, "Mutations require the workroom origin.")
        else:
            response = await call_next(request)
        response.headers.update({
            "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        })
        return response

    @app.exception_handler(PebError)
    async def typed_error(_request: Request, exc: PebError):
        return JSONResponse(exc.envelope(), status_code=getattr(exc, "status", ERROR_STATUS[exc.code]))

    @app.exception_handler(HTTPException)
    async def route_error(_request: Request, exc: HTTPException):
        return _error(exc.status_code, "Unknown route or unsupported method.", ErrorCode.invalid_input)

    @app.post("/api/auth/login")
    async def login(request: Request):
        body = await _json_body(request)
        if set(body) != {"secret"} or not isinstance(body["secret"], str):
            raise _WebError(400, "Expected an operator secret.", ErrorCode.invalid_input)
        if not secrets.compare_digest(body["secret"].encode(), operator_secret.encode()):
            raise _WebError(401, "Invalid operator secret.")
        # Successful login replaces any session presented by this browser.
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        expired = [token for token, record in sessions.items() if record.expires <= clock()]
        for token in expired:
            sessions.pop(token, None)
        if len(sessions) >= 32:
            sessions.pop(next(iter(sessions)))
        token = secrets.token_urlsafe(32)
        current = _Session(secrets.token_urlsafe(32), clock() + session_ttl)
        sessions[token] = current
        response = JSONResponse({"authenticated": True, "csrf_token": current.csrf})
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=False,
                            max_age=session_ttl, path="/")
        return response

    @app.get("/api/auth/session")
    async def get_session(request: Request):
        return {"authenticated": True, "csrf_token": session(request).csrf}

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        csrf(request)
        await _json_body(request)
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
        return response

    def bind(operation: str, method: str):
        async def endpoint(request: Request):
            current_session = session(request)
            if method == "POST":
                csrf(request)
                payload = await _json_body(request)
            else:
                items = list(request.query_params.multi_items())
                if (len(items) > 8 or len({k for k, _ in items}) != len(items)
                        or any(len(k) > 64 or len(v) > 512 for k, v in items)):
                    raise _WebError(400, "Invalid query parameters.", ErrorCode.invalid_input)
                payload = dict(items)
            try:
                path_ids = {k: TypeAdapter(PebId).validate_python(v, strict=True)
                            for k, v in request.path_params.items()}
            except ValueError:
                raise _WebError(400, "Invalid record identifier.", ErrorCode.invalid_input) from None
            try:
                if operation == "run.start":
                    ticket = payload.pop("preview_token", None)
                    if payload.get("provider") == "deepseek":
                        bound = previews.pop(ticket, None) if isinstance(ticket, str) else None
                        fingerprint = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                        if (bound is None or bound[0] != current_session.csrf
                                or bound[1] <= clock() or bound[2] != fingerprint):
                            raise _WebError(409, "Preview this exact hosted run and budget before starting.", ErrorCode.conflict)
                        if payload.get("confirm") is not True:
                            raise _WebError(400, "Explicit start confirmation required.", ErrorCode.invalid_input)
                if operation == "run.resume":
                    existing = await service.request("run.get", path_ids, {})
                    if existing["run"]["manifest"]["provider_kind"] == "deepseek":
                        raise _WebError(409, "Hosted resume requires a new budget preview; use the reviewed CLI flow.", ErrorCode.conflict)
                result = await service.request(operation, path_ids, payload)
                return JSONResponse(jsonable_encoder(result))
            except PebError:
                raise
            except Exception:  # noqa: BLE001 — never expose stack traces, credentials or host paths
                raise PebError(ErrorCode.internal, "The workroom operation failed.") from None
        return endpoint

    @app.post("/api/runs/preview")
    async def preview(request: Request):
        csrf(request)
        current = session(request)
        body = await _json_body(request)
        try:
            result = await service.request("run.preview", {}, body)
        except PebError:
            raise
        except Exception:  # noqa: BLE001 — bounded error envelope, no secret-bearing traceback
            raise PebError(ErrorCode.internal, "Run preview failed.") from None
        scope = result.get("scope", result)
        start_payload = result.get("start_payload")
        if not isinstance(start_payload, dict):
            raise PebError(ErrorCode.internal, "Preview did not supply the normalized start request.")
        token = None
        cost = scope.get("worst_case_cost", {}).get("total_usd_worst_case")
        priced = type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
        if start_payload.get("provider") != "deepseek" or priced:
            for old in list(previews):
                if previews[old][1] <= clock() or previews[old][0] == current.csrf:
                    previews.pop(old)
            if len(previews) >= 64:
                previews.pop(next(iter(previews)))
            token = secrets.token_urlsafe(32)
            previews[token] = (current.csrf, clock() + 300,
                               json.dumps(start_payload, sort_keys=True, separators=(",", ":")))
        return {"scope": scope, "start_payload": start_payload,
                "preview_token": token, "expires_in_seconds": 300,
                "hosted_start_ready": bool(token and priced)}

    @app.get("/api/runs/{run_id}/events")
    async def event_page(request: Request, run_id: str):
        session(request)
        try:
            TypeAdapter(PebId).validate_python(run_id, strict=True)
            query = dict(request.query_params)
            if set(query) - {"cursor", "limit"} or len(query) != len(request.query_params.multi_items()):
                raise ValueError()
            cursor = int(query.get("cursor", "0"))
            limit = int(query.get("limit", "50"))
            if cursor < 0 or not 1 <= limit <= 200:
                raise ValueError()
        except ValueError:
            raise _WebError(400, "Invalid event cursor or limit.", ErrorCode.invalid_input) from None
        result = await service.request("run.get", {"run_id": run_id}, {})
        events = sorted(result["run"]["events"], key=lambda item: item["seq"])
        page = events[cursor:cursor + limit]
        next_cursor = cursor + len(page)
        return {"events": page, "total": len(events), "count": len(page), "cursor": cursor,
                "next_cursor": next_cursor if next_cursor < len(events) else None}

    for method, path, operation in ROUTES:
        app.add_api_route(path, bind(operation, method), methods=[method], name=operation)

    @app.get("/")
    async def index():
        return FileResponse(STATIC_ROOT / "index.html", media_type="text/html")

    @app.get("/assets/{name}")
    async def asset(name: str):
        types = {"app.js": "text/javascript", "style.css": "text/css"}
        if name not in types:
            raise HTTPException(404)
        return FileResponse(STATIC_ROOT / name, media_type=types[name])

    return app

"""Authenticated local real-time API; subjects have no HTTP write credential."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import SecretStr

from ..evidence.realtime import export_shift
from ..providers.credentials import credential_scope, snapshot_credential
from ..rt_contracts import ShiftConfig
from ..runtime.realtime.coordinator import Coordinator
from .app import _json_body

STATIC = Path(__file__).parent / "static/realtime"


class RealtimeService:
    def __init__(self, root: Path, manifest: Path):
        self.root, self.manifest = root, manifest.resolve()
        self.manifest_hash = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.coordinator = None
        self.previews = {}
        self.credentials = {}
        self.create_keys = {}

    async def request(self, operation, path_ids, payload):
        if operation == "health.get":
            return {"profile": "continuous_operation_v1"}
        raise ValueError("use_realtime_routes")

    def provider(self, config):
        if config.provider == "ollama":
            from ..providers.ollama import OllamaProvider

            return OllamaProvider(config.endpoint or "http://127.0.0.1:11434", config.model)
        if config.provider == "deepseek":
            from ..providers.deepseek import DeepSeekProvider

            with credential_scope(snapshot_credential(self.credentials.get("deepseek"))):
                return DeepSeekProvider(model=config.model)
        from ..providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            config.model, self.credentials.get("anthropic"), thinking=config.anthropic_thinking
        )


def attach(app, service: RealtimeService):
    session = app.state.operator_session
    csrf = app.state.operator_csrf

    def current(shift=None):
        c = service.coordinator
        if c is None or c.shift is None or shift is not None and shift != c.shift:
            raise ValueError("unknown_shift")
        return c

    def snapshot_for(request, c):
        result = c.snapshot()
        if session(request).role == "observer":
            result["board"] = {**c.subject, "focus": c.board["focus"]}
            result["reviews"] = []
            result["observer"] = True
        return result

    async def body(request, required, optional=()):
        csrf(request)
        payload = await _json_body(request)
        if set(payload) - set(required) - set(optional) or not set(required) <= set(payload):
            raise ValueError("invalid_fields")
        return payload

    @app.exception_handler(ValueError)
    async def invalid(_request, _exc):
        return JSONResponse(
            {"error": "Request refused; check the command, scope, or current state."},
            status_code=400,
        )

    @app.get("/rt")
    async def page():
        return FileResponse(STATIC / "index.html")

    @app.get("/rt/assets/{name}")
    async def asset(name: str):
        if name not in {"app.js", "style.css"}:
            raise ValueError("unknown_asset")
        return FileResponse(STATIC / name)

    @app.get("/rt/station/index.html")
    async def station(request: Request):
        if session(request).role != "operator":
            raise ValueError("operator_station_required")
        return FileResponse(service.manifest.parent / "dist/experion-station-sim-standalone.html")

    @app.get("/api/rt/status")
    async def status(request: Request):
        session(request)
        return JSONResponse(
            snapshot_for(request, service.coordinator)
            if service.coordinator
            else {"lifecycle": "READY", "kernel_manifest_hash": service.manifest_hash}
        )

    @app.post("/api/rt/credentials")
    async def credential(request: Request):
        payload = await body(request, ["provider", "key"])
        if (
            payload["provider"] not in {"deepseek", "anthropic"}
            or not isinstance(payload["key"], str)
            or len(payload["key"]) > 1024
        ):
            raise ValueError("invalid_credential")
        if payload["key"]:
            service.credentials[payload["provider"]] = SecretStr(payload["key"])
        else:
            service.credentials.pop(payload["provider"], None)
        return {"stored": bool(payload["key"]), "lifetime": "server_process"}

    @app.post("/api/rt/shifts/preview")
    async def preview(request: Request):
        payload = await body(request, ["config"])
        data = dict(payload["config"])
        data.update(
            kernel_manifest=str(service.manifest),
            kernel_manifest_hash=service.manifest_hash,
            hosted_confirmed=False,
        )
        config = ShiftConfig.model_validate(data)
        if config.provider == "scripted":
            raise ValueError("instrument_controls_are_not_model_subjects")
        token = secrets.token_urlsafe(32)
        owner = session(request).csrf
        service.previews = {
            k: v for k, v in service.previews.items() if v[0] > time.monotonic() and v[1] != owner
        }
        service.previews[token] = (time.monotonic() + 300, owner, config)
        return {
            "preview_token": token,
            "config": config.model_dump(),
            "outbound": "Public synthetic plant observations, typed control catalog, mission, and recent public receipts.",
            "scope": "All four synthetic units; bounded controls; native interlocks; human precedence.",
            "budget": {
                "max_calls": config.max_calls,
                "max_output_tokens_per_call": config.max_output_tokens,
                "wall_duration_s": config.wall_duration_s,
            },
            "paid": config.provider != "ollama",
            "price_status": "No price estimate; explicit call/token ceiling is enforced. Monetary caps require a priced provider profile.",
        }

    @app.post("/api/rt/shifts")
    async def create(request: Request):
        payload = await body(
            request, ["preview_token", "idempotency_key", "confirm"], ["confirm_hosted"]
        )
        key = (session(request).csrf, payload["idempotency_key"])
        if key in service.create_keys:
            return service.create_keys[key]
        record = service.previews.get(payload["preview_token"])
        if (
            not record
            or record[0] <= time.monotonic()
            or record[1] != session(request).csrf
            or payload["confirm"] is not True
        ):
            raise ValueError("preview_required")
        config = record[2]
        if config.provider != "ollama" and payload.get("confirm_hosted") is not True:
            raise ValueError("hosted_confirmation_required")
        if service.coordinator is not None:
            raise ValueError("shift_already_exists")
        config = config.model_copy(update={"hosted_confirmed": config.provider != "ollama"})
        provider = service.provider(config)
        metadata = await provider.probe()
        if metadata.get("status") != "ok":
            if hasattr(provider, "close"):
                await provider.close()
            raise ValueError("provider_preflight_failed")
        c = Coordinator(service.root, config, provider)
        try:
            await c.initialize()
            if c.shift is None:
                await c.create()
            if c.lifecycle == "ENDED":
                raise ValueError("ended_shift_requires_new_state_root")
            c.store.event(c.shift, "provider_identity", metadata)
            service.coordinator = c
            await c.start_clock()
        except BaseException:
            await c.close()
            raise
        del service.previews[payload["preview_token"]]
        response = c.snapshot()
        service.create_keys[key] = response
        return response

    @app.get("/api/rt/shifts/{shift}")
    async def get_shift(request: Request, shift: str):
        session(request)
        return JSONResponse(snapshot_for(request, current(shift)))

    @app.get("/api/rt/commands/{command_id}")
    async def get_command(request: Request, command_id: str):
        session(request)
        if session(request).role != "operator":
            raise ValueError("operator_command_read_required")
        return current().store.command(command_id)

    @app.get("/api/rt/command-requests/{request_id}")
    async def reconcile(request: Request, request_id: str):
        if session(request).role != "operator":
            raise ValueError("operator_required")
        c = current()
        row = c.store.db.execute(
            "SELECT id FROM rt_commands WHERE shift=? AND session='operator.session' AND idem=?",
            (c.shift, request_id),
        ).fetchone()
        return c.store.command(row[0]) if row else {"status": "not_received"}

    @app.post("/api/rt/shifts/{shift}/operator-command")
    async def command(request: Request, shift: str):
        payload = await body(request, ["call", "idempotency_key"])
        c = current(shift)
        return c.submit(
            payload["call"], c.observe(), actor="operator", idem=payload["idempotency_key"]
        )

    @app.post("/api/rt/shifts/{shift}/interventions")
    async def intervene(request: Request, shift: str):
        payload = await body(request, ["call", "idempotency_key", "visibility"], ["announcement"])
        if payload["visibility"] not in {"hidden", "announced"}:
            raise ValueError("invalid_visibility")
        text = payload.get("announcement", "Operator announced an intervention.")
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise ValueError("invalid_announcement")
        if not isinstance(payload["call"], dict) or not str(
            payload["call"].get("operation", "")
        ).startswith("instructor."):
            raise ValueError("instructor_operation_required")
        c = current(shift)
        result = c.submit(
            payload["call"], c.observe(), actor="instructor", idem=payload["idempotency_key"]
        )
        if payload["visibility"] == "announced":
            # Public announcement is explicit operator text, never the hidden control payload.
            c.store.event(
                shift, "operator_announcement", {"text": text, "interpretation": "untrusted_data"}
            )
        return result

    @app.post("/api/rt/shifts/{shift}/ownership")
    async def ownership(request: Request, shift: str):
        payload = await body(request, ["target", "take"])
        if type(payload["take"]) is not bool:
            raise ValueError("invalid_take")
        c = current(shift)
        c.ownership(payload["target"], payload["take"])
        return c.snapshot()

    @app.post("/api/rt/shifts/{shift}/reviews/{review_id}")
    async def review(request: Request, shift: str, review_id: str):
        payload = await body(request, ["allow", "digest"])
        if type(payload["allow"]) is not bool:
            raise ValueError("invalid_review")
        c = current(shift)
        c.review(review_id, payload["allow"], payload["digest"])
        return c.snapshot()

    @app.post("/api/rt/shifts/{shift}/agent-control")
    async def agent_control(request: Request, shift: str):
        payload = await body(request, ["operation"])
        c = current(shift)
        c.agent_control(payload["operation"])
        return c.snapshot()

    @app.post("/api/rt/shifts/{shift}/clock-control")
    async def clock_control(request: Request, shift: str):
        payload = await body(request, ["operation"])
        c = current(shift)
        if c.lifecycle == "ENDED":
            raise ValueError("shift_ended")
        if payload["operation"] == "resume":
            await c.start_clock()
        elif payload["operation"] == "pause":
            c.clock_running = False
            c.clock_status = "OPERATOR_PAUSED"
        else:
            raise ValueError("unknown_clock_control")
        c.store.event(shift, "clock_control", payload)
        return c.snapshot()

    @app.post("/api/rt/shifts/{shift}/export")
    async def export(request: Request, shift: str):
        await body(request, [])
        c = current(shift)
        return export_shift(
            c.store, shift, service.root / "exports" / (shift + "." + secrets.token_hex(4))
        )

    @app.get("/api/rt/shifts/{shift}/events")
    async def events(request: Request, shift: str):
        session(request)
        c = current(shift)
        cursor = int(request.headers.get("last-event-id", "0"))

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                session(request)
                rows = c.store.db.execute(
                    "SELECT seq,payload FROM rt_outbox WHERE shift=? AND seq>? AND visibility='public' ORDER BY seq LIMIT 128",
                    (shift, cursor),
                ).fetchall()
                for row in rows:
                    cursor = row["seq"]
                    yield f"id: {cursor}\ndata: {row['payload']}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

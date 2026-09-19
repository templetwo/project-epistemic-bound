"""Explicit launch/doctor/export/replay for the continuous-operation profile."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
from pathlib import Path

from ...evidence.realtime import export_shift, replay_bundle
from ...storage.realtime import RTStore
from .worker import KernelWorker


def main(argv):
    parser = argparse.ArgumentParser(prog="peb rt")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["doctor", "serve", "preview"]:
        sub = commands.add_parser(name)
        sub.add_argument("--kernel", required=True, type=Path)
        if name == "serve":
            sub.add_argument("--state-root", required=True, type=Path)
            sub.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"])
            sub.add_argument("--port", default=8788, type=int)
        if name == "preview":
            sub.add_argument("--config", required=True, type=Path)
    sub = commands.add_parser("commission")
    sub.add_argument("--kernel", required=True, type=Path)
    sub.add_argument("--state-root", required=True, type=Path)
    sub.add_argument("--provider", required=True, choices=["anthropic", "deepseek", "ollama"])
    sub.add_argument("--model", required=True)
    sub.add_argument("--confirm-hosted", action="store_true")
    sub.add_argument(
        "--demo",
        action="store_true",
        help="After passing 20-call qualification, run a fresh 30-minute / 180-call maximum demo",
    )
    sub = commands.add_parser("export")
    sub.add_argument("shift")
    sub.add_argument("--state-root", required=True, type=Path)
    sub.add_argument("--out", required=True, type=Path)
    sub = commands.add_parser("replay")
    sub.add_argument("bundle", type=Path)
    sub.add_argument("--mode", choices=["plant", "evidence"], default="plant")
    args = parser.parse_args(argv)
    if args.command == "commission":
        from .commission import commission

        asyncio.run(commission(args))
    elif args.command == "doctor":

        async def doctor():
            w = KernelWorker(args.kernel, hashlib.sha256(args.kernel.read_bytes()).hexdigest())
            try:
                return await w.start()
            finally:
                await w.close()

        print(json.dumps(asyncio.run(doctor()), indent=2))
    elif args.command == "replay":
        print(
            json.dumps(
                asyncio.run(replay_bundle(args.bundle, plant=args.mode == "plant")), indent=2
            )
        )
    elif args.command == "export":
        store = RTStore(args.state_root)
        try:
            print(json.dumps(export_shift(store, args.shift, args.out), indent=2))
        finally:
            store.close()
    elif args.command == "preview":
        from ...rt_contracts import ShiftConfig

        data = json.loads(args.config.read_text())
        data.update(
            kernel_manifest=str(args.kernel.resolve()),
            kernel_manifest_hash=hashlib.sha256(args.kernel.read_bytes()).hexdigest(),
        )
        config = ShiftConfig.model_validate(data)
        print(
            json.dumps(
                {
                    "config": config.model_dump(),
                    "status": "preview_only_no_model_call",
                    "outbound": "Public synthetic board, mission, tool catalog and public action receipts.",
                },
                indent=2,
            )
        )
    else:
        import fcntl
        from contextlib import asynccontextmanager

        import uvicorn

        from ...web.app import create_workroom
        from ...web.realtime import RealtimeService, attach

        args.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = (args.state_root / "coordinator.lock").open("a+")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A coordinator already owns this state root.") from None
        secret_path = args.state_root / "operator-secret"
        if not secret_path.exists():
            fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32))
        observer_path = args.state_root / "observer-secret"
        if not observer_path.exists():
            fd = os.open(observer_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32))
        service = RealtimeService(args.state_root, args.kernel)
        app = create_workroom(
            service,
            secret_path.read_text(),
            origin=f"http://{args.host}:{args.port}",
            observer_secret=observer_path.read_text(),
        )
        attach(app, service)

        @asynccontextmanager
        async def lifespan(_app):
            from ...rt_contracts import ShiftConfig
            from .coordinator import Coordinator

            store = RTStore(args.state_root)
            old = store.db.execute(
                "SELECT config FROM rt_shifts ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            store.close()
            if old:
                config = ShiftConfig.model_validate_json(old["config"])
                c = Coordinator(args.state_root, config, service.provider(config))
                await c.initialize()
                service.coordinator = c
            yield
            if service.coordinator:
                await service.coordinator.close()

        app.router.lifespan_context = lifespan
        print(
            f"Live operations: http://{args.host}:{args.port}/rt\nOperator sign-in secret file: {secret_path}\nView-only sign-in secret file: {observer_path}"
        )
        uvicorn.run(
            app, host=args.host, port=args.port, access_log=False, timeout_graceful_shutdown=5
        )
        lock.close()
    return 0

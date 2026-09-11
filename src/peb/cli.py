"""`peb` command-line interface (BUILD_SPEC §20).

Every §20 command is registered here so the interface is fixed from the first
commit. Commands whose stage has not been built raise `not_implemented` and exit
non-zero — never a fake success. `doctor` is real from S0 onward.
"""
from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION, __version__
from .config import AppConfig, load_config
from .errors import ErrorCode, NotImplementedYet, PebError
from .storage.repository import SqliteRepository, storage_report

# ----------------------------------------------------------------------------- doctor

def _probe_port(host: str, port: int) -> dict[str, Any]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return {"status": "free", "host": host, "port": port}
    except OSError as e:
        return {"status": "in_use", "host": host, "port": port, "errno": e.errno}
    finally:
        s.close()


def _probe_state_root(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(root)}
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        out["status"] = "writable"
    except OSError as e:
        out["status"] = "unwritable"
        out["error"] = str(e)
    key = root / "keys" / "development_local_hmac.key"
    out["signing_key"] = "present" if key.exists() else "absent (generated on first `peb serve`)"
    return out


def _probe_ollama(cfg: AppConfig) -> dict[str, Any]:
    """Distinct readiness results (§9.2): unreachable / unknown model / not configured / ok."""
    out: dict[str, Any] = {"kind": "ollama", "endpoint": cfg.ollama_endpoint, "model_configured": cfg.ollama_model}
    try:
        import httpx

        with httpx.Client(timeout=2.0, trust_env=False) as client:  # trust_env=False: no inherited proxy (§9.2)
            r = client.get(cfg.ollama_endpoint.rstrip("/") + "/api/tags")
        r.raise_for_status()
        names = [m.get("name") for m in r.json().get("models", [])]
        out["server"] = "reachable"
        out["installed_model_count"] = len(names)
        if cfg.ollama_model is None:
            out["status"] = "model_not_configured"
        elif cfg.ollama_model in names:
            out["status"] = "ok"
        else:
            out["status"] = "unknown_model"
    except Exception as e:  # noqa: BLE001 — every failure is a readiness result, not a crash
        out["server"] = "unreachable"
        out["status"] = "server_unreachable"
        out["error"] = type(e).__name__
    return out


def _dep_versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, str] = {}
    for name in ("pydantic", "fastapi", "uvicorn", "httpx", "pytest"):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "absent"
    return out


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.state_root)
    report = {
        "peb": __version__,
        "schema_version": SCHEMA_VERSION,
        "python": platform.python_version(),
        "executable": sys.executable,
        "dependencies": _dep_versions(),
        "state_root": _probe_state_root(cfg.state_root),
        "storage": storage_report(cfg.state_root),
        "port": _probe_port(cfg.host, cfg.port),
        "signing_mode": cfg.signing_mode,
        "provider": _probe_ollama(cfg),
        "scripted_mode": "available" if True else "unavailable",
    }
    ready_for_scripted = report["state_root"]["status"] == "writable"
    report["ready"] = {"scripted": ready_for_scripted, "local_model": report["provider"]["status"] == "ok"}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ready_for_scripted else 1


# ----------------------------------------------------------------------------- stubs

def _stub(what: str):
    def run(_: argparse.Namespace) -> int:
        raise NotImplementedYet(what)

    return run


def cmd_verify(args: argparse.Namespace) -> int:
    from .evidence.verify import verify_run

    cfg = load_config(args.state_root)
    repo = SqliteRepository.open(cfg.state_root)
    try:
        result = verify_run(repo, args.run_id)
    finally:
        repo.close()
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if result.chain_consistent else 1


def cmd_export(args: argparse.Namespace) -> int:
    from .evidence.export import export_run

    cfg = load_config(args.state_root)
    repo = SqliteRepository.open(cfg.state_root)
    try:
        bundle = export_run(repo, args.run_id, args.out)
    finally:
        repo.close()
    print(json.dumps({"exported": str(bundle)}, indent=2, sort_keys=True))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from datetime import datetime

    from .contracts import StoredEvent
    from .evidence.replay import replay_applied_from_events

    bundle = Path(args.bundle_dir)
    events_path = bundle / "events.jsonl"
    if not events_path.is_file():
        raise PebError(ErrorCode.invalid_input, "bundle is missing events.jsonl",
                       {"bundle": str(bundle)})
    events: list[StoredEvent] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        raw["ts"] = datetime.fromisoformat(raw["ts"])
        from .contracts import Actor, EventType

        raw["event_type"] = EventType(raw["event_type"])
        raw["actor"] = Actor(raw["actor"])
        events.append(StoredEvent.model_validate(raw))
    current = replay_applied_from_events(events)
    print(json.dumps({"resources": current, "provider_invoked": False}, indent=2, sort_keys=True))
    return 0


# ----------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="peb", description="project-epistemic-bound local workroom")
    p.add_argument("--state-root", help="operator state root (default: PEB_STATE_ROOT or ~/.local/share/project-epistemic-bound)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check versions, state root, storage, port, signing mode, provider").set_defaults(fn=cmd_doctor)

    d = sub.add_parser("demo", help="run one scripted instrument demonstration (no model, no network)")
    d.add_argument("--provider", required=True, choices=["scripted"])
    d.add_argument("--case", required=True, choices=["truthful-repair", "authorized-concealment", "forbidden-export"])
    d.set_defaults(fn=_stub("peb demo"))

    s = sub.add_parser("serve", help="start the loopback operator workroom")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(fn=_stub("peb serve"))

    pr = sub.add_parser("providers", help="provider commands").add_subparsers(dest="providers_cmd", required=True)
    pr.add_parser("list", help="show configured/available providers; never downloads a model").set_defaults(fn=_stub("peb providers list"))

    r = sub.add_parser("run", help="run a fresh subject session through the runtime")
    r.add_argument("--provider", required=True, choices=["scripted", "ollama"])
    r.add_argument("--model", required=False)
    r.add_argument("--profile", required=True)
    r.add_argument("--task", required=True)
    r.add_argument("--max-model-calls", type=int, default=16)
    r.set_defaults(fn=_stub("peb run"))

    v = sub.add_parser("verify", help="verify a run's evidence")
    v.add_argument("run_id")
    v.set_defaults(fn=cmd_verify)

    for name, helptext in (("pause", "persist a pause boundary"),
                           ("resume", "explicit resume after rechecks"), ("cancel", "stop new inference/effects")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("run_id")
        sp.set_defaults(fn=_stub(f"peb {name}"))

    e = sub.add_parser("export", help="produce a local evidence bundle; no upload")
    e.add_argument("run_id")
    e.add_argument("--out", required=True)
    e.set_defaults(fn=cmd_export)

    rp = sub.add_parser("replay", help="reconstruct a run from an exported bundle without a model")
    rp.add_argument("bundle_dir")
    rp.set_defaults(fn=cmd_replay)

    st = sub.add_parser("study", help="study planner").add_subparsers(dest="study_cmd", required=True)
    sp = st.add_parser("plan", help="materialize a bounded case schedule; no model execution")
    sp.add_argument("--config", required=True)
    sp.set_defaults(fn=_stub("peb study plan"))
    sr = st.add_parser("run", help="execute a planned study under an explicit budget")
    sr.add_argument("study_id")
    sr.add_argument("--provider", required=True, choices=["scripted", "ollama"])
    sr.add_argument("--model")
    sr.add_argument("--max-model-calls", type=int, required=True)
    sr.set_defaults(fn=_stub("peb study run"))

    rl = sub.add_parser("runs", help="run inventory").add_subparsers(dest="runs_cmd", required=True)
    rl.add_parser("list", help="list runs in the state root").set_defaults(fn=_stub("peb runs list"))
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.fn(args))
    except PebError as e:
        print(json.dumps(e.envelope(), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

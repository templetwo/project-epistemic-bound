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


def _storage_report(state_root: Path) -> dict[str, Any]:
    from .storage.repository import storage_report

    return storage_report(state_root)


def doctor_report(cfg: AppConfig) -> dict[str, Any]:
    """The `peb doctor` report as data; also served as the workroom's `health.get` (INTERFACES §15)."""
    report = {
        "peb": __version__,
        "schema_version": SCHEMA_VERSION,
        "python": platform.python_version(),
        "executable": sys.executable,
        "dependencies": _dep_versions(),
        "state_root": _probe_state_root(cfg.state_root),
        "storage": _storage_report(cfg.state_root),
        "port": _probe_port(cfg.host, cfg.port),
        "signing_mode": cfg.signing_mode,
        "provider": _probe_ollama(cfg),
        "scripted_mode": "available" if True else "unavailable",
    }
    ready_for_scripted = report["state_root"]["status"] == "writable"
    report["ready"] = {"scripted": ready_for_scripted, "local_model": report["provider"]["status"] == "ok"}
    return report


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(load_config(args.state_root))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"]["scripted"] else 1


# ----------------------------------------------------------------------------- providers list

def cmd_providers_list(args: argparse.Namespace) -> int:
    """Configured/available providers. Reads /api/tags only; never pulls a model (§20)."""
    cfg = load_config(args.state_root)
    ollama: dict[str, Any] = _probe_ollama(cfg)
    ollama["selectable_for_measured_runs"] = ollama["status"] == "ok"
    report = {"providers": [
        {"kind": "scripted", "status": "available", "synthetic": True,
         "note": "deterministic fixtures; never reportable as a measured model result"},
        {**ollama, "note": "explicit endpoint and model id; no automatic pull, no fallback"},
    ]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


# ----------------------------------------------------------------------------- demo (§0.2, §20)

def cmd_demo(args: argparse.Namespace) -> int:
    import asyncio

    from .runtime.bootstrap import run_scripted_demo, summarize_outcome_columns

    cfg = load_config(args.state_root)
    summary = asyncio.run(run_scripted_demo(cfg.state_root, args.case))
    summary["outcome_columns"] = summarize_outcome_columns(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    ok = summary["verification"]["chain_consistent"] and summary["status"] in ("completed", "declined")
    return 0 if ok else 1


# ----------------------------------------------------------------------------- run (§20, model observation)

def cmd_run(args: argparse.Namespace) -> int:
    import asyncio

    from .runtime.bootstrap import run_model_observation, summarize_outcome_columns

    cfg = load_config(args.state_root)
    if args.provider != "ollama":
        raise PebError(ErrorCode.invalid_input, "peb run observes a configured local model; use `peb demo` for scripted controls")
    if not args.model:
        raise PebError(ErrorCode.invalid_input, "--model is required: an explicit installed model id, never a default")
    summary = asyncio.run(run_model_observation(cfg.state_root, model=args.model, profile_id=args.profile,
                                                task_id=args.task, max_model_calls=args.max_model_calls,
                                                endpoint=cfg.ollama_endpoint))
    summary["outcome_columns"] = summarize_outcome_columns(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["verification"]["chain_consistent"] else 1


def cmd_resume(args: argparse.Namespace) -> int:
    import asyncio

    from .runtime.bootstrap import resume_run, summarize_outcome_columns

    cfg = load_config(args.state_root)
    summary = asyncio.run(resume_run(cfg.state_root, args.run_id, endpoint=cfg.ollama_endpoint))
    summary["outcome_columns"] = summarize_outcome_columns(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["verification"]["chain_consistent"] else 1


def cmd_serve(args: argparse.Namespace) -> int:
    """§20 `peb serve`: 1/3 builds the WorkroomService and hands it to seat 2/3's `create_workroom`
    (INTERFACES §15). Loopback only; the operator secret lives in the state root."""
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        raise PebError(ErrorCode.invalid_input, "peb serve binds loopback only", {"host": args.host})
    try:
        from .web import create_workroom  # seat 2/3
    except ImportError as e:
        raise PebError(ErrorCode.not_implemented,
                       "peb serve is not implemented in this checkout: the web lane has not landed "
                       "create_workroom(service, operator_secret, origin) (INTERFACES §15)", {"missing": str(e)}) from e
    from .config import load_or_create_operator_secret
    from .runtime.service import WorkroomService

    cfg = load_config(args.state_root)
    secret = load_or_create_operator_secret(cfg.state_root)
    service = WorkroomService(cfg.state_root, ollama_endpoint=cfg.ollama_endpoint)
    app = create_workroom(service, secret, origin=f"http://{args.host}:{args.port}")
    import uvicorn

    print(json.dumps({"serving": f"http://{args.host}:{args.port}", "state_root": str(cfg.state_root),
                      "operator_secret": "in state root (never printed)"}, sort_keys=True))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _review_cmd(name: str):
    def run(args: argparse.Namespace) -> int:
        from .contracts import Actor

        try:
            from .storage.repository import (
                SqliteRepository,  # noqa: F401  (presence check: boundary lane merged?)
            )
        except ImportError as e:
            raise PebError(ErrorCode.not_implemented,
                           f"peb review {name} is not implemented in this checkout: the boundary lane is not merged here",
                           {"missing": str(e)}) from e
        from .runtime.bootstrap import list_reviews, resolve_review_from_records

        cfg = load_config(args.state_root)
        if name == "list":
            print(json.dumps(list_reviews(cfg.state_root, args.run_id), indent=2, sort_keys=True))
            return 0
        by = Actor.scripted_reviewer if getattr(args, "scripted_reviewer", False) else Actor.operator
        out = resolve_review_from_records(cfg.state_root, args.run_id, args.review_id, name, by=by, note=args.note)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    return run


def _set_status_cmd(status_name: str):
    def run(args: argparse.Namespace) -> int:
        from .contracts import RunStatus

        try:
            from .storage.repository import SqliteRepository
        except ImportError as e:
            raise PebError(ErrorCode.not_implemented,
                           f"peb {status_name} is not implemented in this checkout: the boundary lane is not merged here",
                           {"missing": str(e)}) from e
        from .runtime.controls import cancel_run, pause_run

        cfg = load_config(args.state_root)
        repo = SqliteRepository.open(cfg.state_root)
        try:
            ev = pause_run(repo, args.run_id) if status_name == "pause" else cancel_run(repo, args.run_id)
            target = RunStatus.paused if status_name == "pause" else RunStatus.cancelled
            print(json.dumps({"run_id": args.run_id, "requested": status_name, "durable_status": str(target),
                              "event": {"seq": ev.seq, "type": str(ev.event_type), "event_id": ev.event_id},
                              "note": "the supervisor honours this boundary before its next model call; "
                                      "effects already committed remain recorded"}, sort_keys=True))
            return 0
        finally:
            repo.close()
    return run


# ----------------------------------------------------------------------------- stubs

def _stub(what: str):
    def run(_: argparse.Namespace) -> int:
        raise NotImplementedYet(what)

    return run


def cmd_verify(args: argparse.Namespace) -> int:
    from .evidence.verify import verify_run
    from .storage.repository import SqliteRepository

    cfg = load_config(args.state_root)
    repo = SqliteRepository.open(cfg.state_root)
    try:
        result = verify_run(repo, args.run_id, checkpoint=None)
    finally:
        repo.close()
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if result.chain_consistent and not result.failures else 1


def cmd_export(args: argparse.Namespace) -> int:
    from .evidence.export import export_run
    from .storage.repository import SqliteRepository

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


def cmd_runs_list(args: argparse.Namespace) -> int:
    from .storage.repository import SqliteRepository

    cfg = load_config(args.state_root)
    repo = SqliteRepository.open(cfg.state_root)
    try:
        items = repo.list_runs()
    finally:
        repo.close()
    print(json.dumps(
        [
            {
                "run_id": item.run_id,
                "status": item.status,
                "mode": item.mode,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
        indent=2,
        sort_keys=True,
    ))
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
    d.set_defaults(fn=cmd_demo)

    s = sub.add_parser("serve", help="start the loopback operator workroom")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(fn=cmd_serve)

    pr = sub.add_parser("providers", help="provider commands").add_subparsers(dest="providers_cmd", required=True)
    pr.add_parser("list", help="show configured/available providers; never downloads a model").set_defaults(fn=cmd_providers_list)

    r = sub.add_parser("run", help="run a fresh subject session through the runtime")
    r.add_argument("--provider", required=True, choices=["scripted", "ollama"])
    r.add_argument("--model", required=False)
    r.add_argument("--profile", required=True)
    r.add_argument("--task", required=True)
    r.add_argument("--max-model-calls", type=int, default=16)
    r.set_defaults(fn=cmd_run)

    v = sub.add_parser("verify", help="verify a run's evidence")
    v.add_argument("run_id")
    v.set_defaults(fn=cmd_verify)
    for name, helptext in (("pause", "persist a pause boundary"), ("cancel", "stop new inference/effects")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("run_id")
        sp.set_defaults(fn=_set_status_cmd(name))
    rs = sub.add_parser("resume", help="explicit resume after rechecks (rebuilds the run from records)")
    rs.add_argument("run_id")
    rs.set_defaults(fn=cmd_resume)

    rv = sub.add_parser("review", help="§13 review queue: list, acknowledge, allow or deny a held proposal") \
        .add_subparsers(dest="review_cmd", required=True)
    rvl = rv.add_parser("list", help="show the run's review queue from records")
    rvl.add_argument("run_id")
    rvl.set_defaults(fn=_review_cmd("list"))
    for name, helptext in (("ack", "mark a pending review read (acknowledgement is not approval)"),
                           ("allow", "issue an approval and execute the held proposal, then pause the run"),
                           ("deny", "record the operator's denial, then pause the run")):
        rvp = rv.add_parser(name, help=helptext)
        rvp.add_argument("run_id")
        rvp.add_argument("review_id")
        rvp.add_argument("--note", default="")
        rvp.add_argument("--scripted-reviewer", action="store_true",
                         help="label the resolver as a scripted reviewer (local demo only; NOT human review)")
        rvp.set_defaults(fn=_review_cmd(name))

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
    rl.add_parser("list", help="list runs in the state root").set_defaults(fn=cmd_runs_list)
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

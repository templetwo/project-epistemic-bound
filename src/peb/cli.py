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
from .errors import ErrorCode, PebError

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
    import os as _os
    deepseek = {"kind": "deepseek", "endpoint": cfg.deepseek_endpoint, "key_env": cfg.deepseek_api_key_env,
                "key": "present" if _os.environ.get(cfg.deepseek_api_key_env) else "absent",
                "status": "configured" if _os.environ.get(cfg.deepseek_api_key_env) else "key_absent",
                "network": "not contacted by this command", "paid": True, "selectable_for_measured_runs": True,
                "note": "hosted; explicit https endpoint and model id; no fallback; run `peb run --provider deepseek "
                        "--dry-run ...` to see the outbound-data scope and maximum budget before any paid request (ADR-017)"}
    report = {"providers": [
        {"kind": "scripted", "status": "available", "synthetic": True,
         "note": "deterministic fixtures; never reportable as a measured model result"},
        {**ollama, "note": "explicit endpoint and model id; no automatic pull, no fallback"},
        deepseek,
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
    if args.provider not in ("ollama", "deepseek"):
        raise PebError(ErrorCode.invalid_input, "peb run observes a configured model provider; use `peb demo` for scripted controls")
    if not args.model:
        raise PebError(ErrorCode.invalid_input, "--model is required: an explicit model id, never a default")
    endpoint = cfg.ollama_endpoint if args.provider == "ollama" else cfg.deepseek_endpoint
    if getattr(args, "dry_run", False):
        # ADR-017: what would leave the machine and the maximum budget, with NO network call and NO state change.
        from .runtime.bootstrap import outbound_scope

        rates = None
        if args.input_rate is not None and args.output_rate is not None:
            rates = {"input_cache_miss_per_mtok": args.input_rate, "output_per_mtok": args.output_rate,
                     "provenance": args.rates_provenance or "supplied on the command line; not verified by this software"}
        scope = outbound_scope(provider_kind=args.provider, endpoint=endpoint, model=args.model, profile_id=args.profile,
                               task_id=args.task, max_model_calls=args.max_model_calls, max_output_tokens=args.max_tokens,
                               max_input_chars=args.max_input_chars, rates=rates, thinking=args.thinking)
        print(json.dumps({"dry_run": True, **scope}, indent=2, sort_keys=True))
        return 0
    summary = asyncio.run(run_model_observation(cfg.state_root, model=args.model, profile_id=args.profile,
                                                task_id=args.task, max_model_calls=args.max_model_calls,
                                                endpoint=endpoint, provider_kind=args.provider,
                                                max_output_tokens=args.max_tokens, max_input_chars=args.max_input_chars,
                                                thinking=args.thinking))
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


def build_study_plan(config: dict) -> dict:
    """§20 `peb study plan` / service `study.plan`: seat 2/3's `peb.evaluation.planner.build_plan` behind the
    §15 seam. Planning opens no repository and no provider and writes nothing; a plan is a schedule, not a receipt.
    not_implemented when the planner lane is absent; an invalid or over-cap config is invalid_input."""
    try:
        from .evaluation.planner import build_plan
    except ImportError as e:
        raise PebError(ErrorCode.not_implemented, "peb study plan is not implemented in this checkout: the planner lane "
                       "(peb.evaluation.planner) is not merged here", {"missing": str(e)}) from e
    try:
        return build_plan(config)
    except (ValueError, TypeError) as e:  # pydantic ValidationError is a ValueError
        detail = getattr(e, "errors", None)
        errors = ([{"loc": list(map(str, d.get("loc", ()))), "msg": str(d.get("msg", ""))[:200]} for d in detail(include_url=False)][:10]
                  if callable(detail) else [{"msg": str(e)[:300]}])
        raise PebError(ErrorCode.invalid_input, "study config refused by the planner", {"errors": errors}) from None


def cmd_study_plan(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .contracts import strict_json_loads

    path = Path(args.config)
    if not path.is_file():
        raise PebError(ErrorCode.invalid_input, "study config file not found", {"config": str(path)})
    try:
        config = strict_json_loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PebError(ErrorCode.invalid_input, "study config is not strict JSON", {"config": str(path), "reason": str(e)[:200]}) from None
    plan = build_study_plan(config)
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        if out.exists():
            raise PebError(ErrorCode.conflict, "plan file already exists; a plan is never overwritten", {"out": str(out)})
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as fh:
            fh.write(rendered)
        print(json.dumps({"study_id": plan["study_id"], "plan_hash": plan["plan_hash"], "planned": plan["counts"]["planned"],
                          "model_calls_ceiling": plan["budget"]["model_calls_ceiling"], "out": str(out)}, sort_keys=True))
        return 0
    print(rendered, end="")
    return 0


def _read_plan_file(path_str: str) -> dict:
    """A plan file has its OWN bound (`runtime.study.PLAN_FILE_MAX_BYTES`, 4 MiB — every supported schedule fits with
    room): the decision ceiling is for subject output, not schedules (2/3's #28655: a valid 480-trial plan is 196 KB).
    The read is bounded BEFORE parsing; strict JSON (no duplicate keys, no NaN); an object."""
    from pathlib import Path

    from .contracts import strict_json_loads
    from .runtime.study import PLAN_FILE_MAX_BYTES

    path = Path(path_str)
    if not path.is_file():
        raise PebError(ErrorCode.invalid_input, "study plan file not found", {"plan": str(path)})
    with path.open("rb") as fh:
        raw = fh.read(PLAN_FILE_MAX_BYTES + 1)
    if len(raw) > PLAN_FILE_MAX_BYTES:
        raise PebError(ErrorCode.invalid_input, f"study plan file exceeds {PLAN_FILE_MAX_BYTES} bytes; not parsed",
                       {"plan": str(path), "limit_bytes": PLAN_FILE_MAX_BYTES})
    try:
        plan = strict_json_loads(raw.decode("utf-8"), ceiling_bytes=PLAN_FILE_MAX_BYTES)
    except (ValueError, UnicodeDecodeError) as e:
        raise PebError(ErrorCode.invalid_input, "study plan is not strict JSON", {"plan": str(path), "reason": str(e)[:200]}) from None
    if not isinstance(plan, dict):
        raise PebError(ErrorCode.invalid_input, "study plan must be a JSON object", {"plan": str(path)})
    return plan


def cmd_study_preview(args: argparse.Namespace) -> int:
    """`peb study preview <study-id> --plan FILE --max-model-calls N [--input-rate --output-rate --rates-provenance]`:
    the pre-launch scope of the whole plan (outbound data and maximum budget per unique condition, summed) with NO
    network call and NO state change — what an operator sees before a hosted `peb study run … --confirm-hosted`."""
    from .runtime.study import preview_study

    cfg = load_config(args.state_root)
    plan = _read_plan_file(args.plan)
    if plan.get("study_id") != args.study_id:
        raise PebError(ErrorCode.invalid_input, "the typed study id does not match the plan file",
                       {"typed": str(args.study_id)[:80], "plan": str(plan.get("study_id"))[:80]})
    rates = None
    if (args.input_rate is None) != (args.output_rate is None):
        raise PebError(ErrorCode.invalid_input, "--input-rate and --output-rate must be supplied together (USD per 1M tokens)")
    if args.input_rate is not None:
        rates = {"input_cache_miss_per_mtok": args.input_rate, "output_per_mtok": args.output_rate,
                 "provenance": args.rates_provenance or "supplied on the command line; not verified by this software"}
    out = preview_study(plan, max_model_calls=args.max_model_calls, ollama_endpoint=cfg.ollama_endpoint,
                        deepseek_endpoint=cfg.deepseek_endpoint, rates=rates)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_study_run(args: argparse.Namespace) -> int:
    """§20 `peb study run <study-id> --plan FILE --max-model-calls N --confirm [--confirm-hosted]` (board #28563/#28565):
    seat 2/3's coordinator admits ONE execution of the displayed plan (exact rebuild equality; explicit cap covering
    the ceiling; duplicate → conflict before any driver call) and dispatches this seat's trial driver in plan order;
    every trial is a fresh recorded run. The typed study id must match the plan file. Exit 0 only when the journal
    says `completed`; a partial study exits 1 with the journal printed. Nothing is retried."""
    import asyncio

    from .runtime.study import bind_trial_driver, coordinator

    cfg = load_config(args.state_root)
    module = coordinator()  # the lane rule first: an absent coordinator is not_implemented whatever the arguments
    plan = _read_plan_file(args.plan)
    if plan.get("study_id") != args.study_id:
        raise PebError(ErrorCode.invalid_input, "the typed study id does not match the plan file",
                       {"typed": str(args.study_id)[:80], "plan": str(plan.get("study_id"))[:80]})
    if not args.confirm:
        raise PebError(ErrorCode.invalid_input, "explicit --confirm is required: a plan is a schedule, not a launch")
    config = plan.get("config")
    provider = config.get("provider") if isinstance(config, dict) else None
    if provider == "deepseek" and not args.confirm_hosted:
        raise PebError(ErrorCode.invalid_input, "hosted study refused: --confirm-hosted is required for a deepseek plan "
                       "(paid calls); nothing was created", {"provider": "deepseek"})
    driver = bind_trial_driver(cfg.state_root, ollama_endpoint=cfg.ollama_endpoint, deepseek_endpoint=cfg.deepseek_endpoint,
                               confirm_hosted=bool(args.confirm_hosted))
    report = asyncio.run(module.run_study(cfg.state_root, plan, max_model_calls=args.max_model_calls, confirm=True,
                                          run_trial=driver))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 1


def cmd_study_get(args: argparse.Namespace) -> int:
    """`peb study get <study-id>`: the durable journal, read-only; an abandoned execution reads as `interrupted`."""
    from .runtime.study import coordinator

    cfg = load_config(args.state_root)
    print(json.dumps(coordinator().get_study(cfg.state_root, args.study_id), indent=2, sort_keys=True))
    return 0


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


IN_FLIGHT = ("running", "waiting_review")


def probe_host_for(host: str) -> str:
    """The address to probe/connect for a server bound to `host` (loopback only, ADR-019)."""
    return "127.0.0.1" if host == "localhost" else host


def _spawn_workroom(host: str, port: int, state_root: Path, *, popen=None, connect=None, sleep=None, probe=None, deadline_s: float = 15.0):
    """Start the EXISTING `peb serve` as a child of this interpreter on an explicit loopback host/port and the
    RESOLVED state root (forwarded both as `--state-root` argv and as PEB_STATE_ROOT in the child's environment —
    2/3's #28502: an explicit CLI root must override anything inherited). Waits until the port listens."""
    import os
    import socket
    import subprocess
    import sys
    import time as _time

    popen = popen or subprocess.Popen
    connect = connect or socket.create_connection
    sleep = sleep or _time.sleep
    probe = probe or _probe_port   # injectable so no test depends on a real port being free
    # The wait below returns as soon as SOMETHING listens on the port. If another workroom is already there,
    # connect() wins the race against our child's failure to bind, and the cockpit would attach to a stranger's
    # server while reporting our child's pid — a pid whose `kill` stops nothing. So refuse before spawning:
    # a port that is not free is not ours to claim (found while Anthony test-drove the README quickstart with
    # the previous night's workroom still on 8787). Residual window between this probe and the child's bind is
    # milliseconds and ends in the honest "child exited before it listened" error below.
    taken = probe(probe_host_for(host), port)
    if taken.get("status") != "free":
        raise PebError(ErrorCode.conflict,
                       f"something is already listening on {host}:{port}; the cockpit will not adopt a workroom it did not start",
                       {"host": host, "port": port, "attach_instead": f"peb tui --attach http://{probe_host_for(host)}:{port}",
                        "or": "choose a free port with --port"})
    argv = [sys.executable, "-c",
            f"from peb.cli import main; raise SystemExit(main(['--state-root', {str(state_root)!r}, 'serve', '--host', {host!r}, '--port', {str(port)!r}]))"]
    env = {**os.environ, "PEB_STATE_ROOT": str(state_root)}
    server = popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    deadline = _time.monotonic() + deadline_s
    probe_host = probe_host_for(host)
    while _time.monotonic() < deadline:
        if server.poll() is not None:
            raise PebError(ErrorCode.provider_unavailable, "the workroom child process exited before it listened",
                           {"exit_code": server.returncode})
        try:
            with connect((probe_host, port), timeout=0.5):
                return server
        except OSError:
            sleep(0.2)
    server.terminate()
    raise PebError(ErrorCode.provider_unavailable, "the workroom did not start listening in time", {"host": host, "port": port})


def _after_quit(server, runs: list[dict], origin: str, *, confirmed: bool = True) -> dict | None:
    """Ownership contract for `--serve` (2/3's #28502/#28511): no inventory read is a shutdown interlock — another
    client can start a run after any read, and the cockpit may quit before its first inventory. So quitting the
    cockpit ALWAYS detaches a successfully started child workroom and reports how to reach or stop it explicitly;
    nothing is terminated automatically here. (Startup failures are cleaned up by `_spawn_workroom`, which owns the
    child until it listens.) The inventory read at quit is information for the operator, never permission."""
    if server is None:
        return None
    in_flight = [str(r.get("run_id")) for r in runs if r.get("status") in IN_FLIGHT]
    return {"workroom_left_running": origin, "pid": server.pid,
            "in_flight_at_quit": in_flight if confirmed else "unconfirmed (the inventory could not be read at quit)",
            "reattach": f"peb tui --attach {origin}", "stop": f"kill {server.pid}  # when you are done with it; in-flight runs would be interrupted"}


def _run_cockpit(origin: str, secret: str) -> tuple[list[dict], bool]:
    """Run the app; return the inventory it read at quit and whether that read succeeded."""
    from .tui.app import CockpitApp
    from .tui.http_transport import HttpWorkroomTransport

    app = CockpitApp(HttpWorkroomTransport(origin), secret=secret)
    app.run()
    return list(app.last_inventory), bool(app.inventory_confirmed)


def cmd_tui(args: argparse.Namespace) -> int:
    """`peb tui` (ADR-019): the terminal cockpit, an authenticated client of the loopback workroom. `--attach URL`
    joins a workroom that is already serving; `--serve` starts the EXISTING `peb serve` as a child on the given
    loopback host/port and the resolved state root, then attaches (never a second runtime). The operator secret is
    read from the protected state root when it is there, else prompted without echo; it is never a command-line
    argument and never printed. On quit the cockpit detaches: a child workroom it started is always left running and
    reported with its pid and stop command; nothing stops a run by the cockpit closing."""
    import getpass

    from .config import OPERATOR_SECRET_FILE
    from .tui.http_transport import canonical_origin
    from .tui.transport import TransportError

    url = args.attach or f"http://{args.host}:{args.port}"
    try:
        origin = canonical_origin(url)
    except TransportError as e:
        raise PebError(ErrorCode.invalid_input, "peb tui attaches to an explicit http loopback host and port only", {"url": url}) from e
    cfg = load_config(args.state_root)
    server = None
    if args.serve:
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            raise PebError(ErrorCode.invalid_input, "peb tui --serve binds loopback only", {"host": args.host})
        server = _spawn_workroom(args.host, args.port, Path(cfg.state_root))
    secret_path = Path(cfg.state_root) / OPERATOR_SECRET_FILE
    if secret_path.exists():
        secret = secret_path.read_text(encoding="utf-8").strip()
    else:
        secret = getpass.getpass("operator secret (from operator.secret in the workroom's state root; not echoed): ")
    runs: list[dict] = []
    confirmed = False
    try:
        runs, confirmed = _run_cockpit(origin, secret)
        del secret
    finally:
        notice = _after_quit(server, runs, origin, confirmed=confirmed)
        if notice is not None:
            print(json.dumps(notice, sort_keys=True))
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
    from .evidence.bundle import inspect_bundle

    report = inspect_bundle(args.bundle_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verification"]["summary"] != "failed" else 1


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

    t = sub.add_parser("tui", help="terminal cockpit over the loopback workroom (ADR-019): --attach URL or --serve")
    t.add_argument("--attach", metavar="URL", help="join a workroom already serving at this explicit http loopback URL")
    t.add_argument("--serve", action="store_true", help="start the existing `peb serve` as a child process, then attach")
    t.add_argument("--host", default="127.0.0.1")
    t.add_argument("--port", type=int, default=8787)
    t.set_defaults(fn=cmd_tui)

    pr = sub.add_parser("providers", help="provider commands").add_subparsers(dest="providers_cmd", required=True)
    pr.add_parser("list", help="show configured/available providers; never downloads a model").set_defaults(fn=cmd_providers_list)

    r = sub.add_parser("run", help="run a fresh subject session through the runtime")
    r.add_argument("--provider", required=True, choices=["scripted", "ollama", "deepseek"])
    r.add_argument("--model", required=False)
    r.add_argument("--profile", required=True)
    r.add_argument("--task", required=True)
    r.add_argument("--max-model-calls", type=int, default=16)
    r.add_argument("--max-tokens", type=int, default=None, help="max output tokens per call (Limits.max_output_tokens)")
    r.add_argument("--dry-run", action="store_true",
                   help="print the outbound-data scope and maximum budget; no network, no state change (ADR-017)")
    r.add_argument("--max-input-chars", type=int, default=None, help="enforced whole-request input maximum (chars)")
    r.add_argument("--thinking", choices=["enabled", "disabled"], default="enabled",
                   help="hosted provider thinking mode (DeepSeek); pinned in the manifest, effective setting read back per "
                        "response, reasoning retained as evidence (ADR-017 addendum 2). Ignored by Ollama.")
    r.add_argument("--input-rate", type=float, default=None, help="USD per 1M input tokens at the cache-MISS (peak) rate, for the dry-run worst case")
    r.add_argument("--output-rate", type=float, default=None, help="USD per 1M output tokens, for the dry-run worst case")
    r.add_argument("--rates-provenance", default=None, help="where the rates came from (recorded verbatim in the report)")
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
    sp.add_argument("--out", default=None, help="write the plan to a NEW file (never overwrites an existing plan)")
    sp.set_defaults(fn=cmd_study_plan)
    sr = st.add_parser("run", help="execute a displayed plan under an explicit budget; every trial is a fresh recorded run")
    sr.add_argument("study_id", help="the plan's study_id, typed by the operator; must match --plan")
    sr.add_argument("--plan", required=True, help="the plan file written by `peb study plan --out` (provider and model are in it)")
    sr.add_argument("--max-model-calls", type=int, required=True, help="explicit total decision-call cap; must cover the plan's ceiling")
    sr.add_argument("--confirm", action="store_true", help="explicit launch confirmation; a plan alone starts nothing")
    sr.add_argument("--confirm-hosted", action="store_true", help="additionally required for a hosted (deepseek) plan: paid calls")
    sr.set_defaults(fn=cmd_study_run)
    sg = st.add_parser("get", help="read a study's durable journal (rows, results, counts); an abandoned run reads as interrupted")
    sg.add_argument("study_id")
    sg.set_defaults(fn=cmd_study_get)
    spv = st.add_parser("preview", help="the whole plan's outbound scope and maximum budget before a hosted run; no network, no state change")
    spv.add_argument("study_id", help="the plan's study_id, typed by the operator; must match --plan")
    spv.add_argument("--plan", required=True)
    spv.add_argument("--max-model-calls", type=int, required=True, help="the cap you would pass to `study run`; must cover the plan's ceiling")
    spv.add_argument("--input-rate", type=float, default=None, help="USD per 1M input tokens at the cache-MISS (peak) rate")
    spv.add_argument("--output-rate", type=float, default=None, help="USD per 1M output tokens")
    spv.add_argument("--rates-provenance", default=None, help="where the rates came from (recorded verbatim; not verified)")
    spv.set_defaults(fn=cmd_study_preview)

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

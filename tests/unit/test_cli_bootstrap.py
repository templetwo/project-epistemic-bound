"""S0 bootstrap: `peb doctor` is real; every other §20 command fails honestly."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from peb import SCHEMA_VERSION, __version__
from peb.cli import build_parser, main
from peb.config import DEFAULT_STATE_ROOT, resolve_state_root


def test_doctor_reports_and_uses_temporary_state_root(state_root: Path, capsys):
    rc = main(["doctor"])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert rc == 0
    assert report["peb"] == __version__
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["state_root"]["path"] == str(state_root)
    assert report["state_root"]["status"] == "writable"
    assert state_root.is_dir()
    # ISO-02: the operator's default root was not created by a test.
    assert resolve_state_root() == state_root
    assert not (DEFAULT_STATE_ROOT.expanduser() / ".write-probe").exists()
    # Provider unavailability is a readiness result, not a failure (§20).
    assert report["provider"]["status"] == "server_unreachable"
    assert report["ready"] == {"scripted": True, "local_model": False}
    assert report["storage"]["status"] == "ok"
    assert report["storage"]["backend"] == "sqlite"
    assert report["storage"]["migrations"] == [1, 2]
    assert report["signing_mode"] == "development_local_hmac"


def test_the_port_probe_never_calls_a_loopback_it_cannot_resolve_occupied():
    """External review of 6d56684, F15: AF_INET was hardcoded, so probing ::1 raised gaierror — an OSError
    subclass — and every `peb tui --serve --host ::1` was refused as occupied on a free port."""
    from peb.cli import _probe_port

    # The regression guard is the negative: a free IPv6 loopback must never be reported occupied. Whether it
    # comes back `free` or `unknown` depends on the host's IPv6 support, and both are honest answers.
    assert _probe_port("::1", 8799)["status"] in ("free", "unknown")
    assert _probe_port("127.0.0.1", 8799)["status"] == "free"
    # A name that cannot resolve yields no opinion at all, rather than a guess in either direction.
    unresolvable = _probe_port("no-such-host.invalid", 8799)
    assert unresolvable["status"] == "unknown" and "reason" in unresolvable


def test_spawn_refuses_only_a_port_proven_occupied(tmp_path):
    """`unknown` must fall through to the child's own bind; refusing on it is what broke --host ::1."""
    from peb import cli
    from peb.errors import ErrorCode, PebError

    calls: list[object] = []

    def never_spawn(*a, **k):
        calls.append(a)
        raise AssertionError("should not spawn in this test")

    with pytest.raises(PebError) as occupied:
        cli._spawn_workroom(tmp_path, "127.0.0.1", 8799, popen=never_spawn,
                            probe=lambda *_a: {"status": "in_use", "errno": 48})
    assert occupied.value.code == ErrorCode.conflict and calls == []

    # `unknown` is not a refusal: the spawn proceeds and fails (or succeeds) on the child's real bind.
    with pytest.raises(Exception) as proceeded:
        cli._spawn_workroom(tmp_path, "::1", 8799, popen=never_spawn,
                            probe=lambda *_a: {"status": "unknown", "reason": "gaierror"})
    assert not isinstance(proceeded.value, PebError) or proceeded.value.code != ErrorCode.conflict


def test_doctor_carries_the_installed_model_names_it_already_read(state_root: Path, monkeypatch):
    """The operator cannot choose an explicit model id from a count. An unreachable server lists nothing."""
    import httpx

    from peb import cli
    from peb.config import load_config

    real_client = httpx.Client

    def tags(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "b:2"}, {"name": "a:1"}, {"name": ""}, {}]})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(tags), **kw))
    reachable = cli._probe_ollama(load_config(state_root))
    # Sorted, nameless entries dropped, and the count still agrees with the list it came from.
    assert reachable["installed_models"] == ["a:1", "b:2"]
    assert reachable["installed_model_count"] == 2
    # No model is chosen for the operator: an installed list is not a default.
    assert reachable["status"] == "model_not_configured"
    assert "model" not in reachable or reachable["model_configured"] is None

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(refused), **kw))
    unreachable = cli._probe_ollama(load_config(state_root))
    assert unreachable["status"] == "server_unreachable"
    assert "installed_models" not in unreachable and "installed_model_count" not in unreachable


def test_hosted_catalog_is_the_providers_own_current_list_and_only_on_request(state_root: Path, monkeypatch):
    """Anthony: "make sure the deepseek model choices are validated to actual current models"."""
    import asyncio

    import httpx

    from peb import cli
    from peb.config import load_config

    seen: list[str] = []

    def catalog(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.url.host == "api.deepseek.com"  # the pinned host, never a redirect target
        return httpx.Response(200, json={"data": [{"id": "deepseek-reasoner"}, {"id": "deepseek-chat"}]})

    cfg = load_config(state_root)
    monkeypatch.setenv(cfg.deepseek_api_key_env, "not-a-real-key-for-this-test")

    # The catalog alone: a listing is not a question about any id, so no id is judged.
    listed = asyncio.run(cli.probe_hosted_catalog(cfg, None, transport=httpx.MockTransport(catalog)))
    assert listed["available_models"] == ["deepseek-chat", "deepseek-reasoner"]
    assert listed["status"] == "listed" and listed["model"] is None
    assert seen == ["/models"]

    # An id that IS current, and one that is not — the same verdict the run path reaches, reached earlier.
    current = asyncio.run(cli.probe_hosted_catalog(cfg, "deepseek-chat", transport=httpx.MockTransport(catalog)))
    assert current["status"] == "ok" and current["model"] == "deepseek-chat"
    stale = asyncio.run(cli.probe_hosted_catalog(cfg, "deepseek-v2-imagined", transport=httpx.MockTransport(catalog)))
    assert stale["status"] == "unknown_model" and stale["available_models"] == ["deepseek-chat", "deepseek-reasoner"]

    # An entry with no id is not a model called "None" (review F6).
    def ragged(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}, {"object": "model"}, {"id": ""}]})

    assert asyncio.run(cli.probe_hosted_catalog(cfg, None, transport=httpx.MockTransport(ragged)))["available_models"] == ["deepseek-chat"]

    # The key is never returned, only whether one is present.
    assert set(listed) & {"key", "endpoint_host"} == {"key", "endpoint_host"}
    assert "not-a-real-key-for-this-test" not in json.dumps(listed)

    # No key: no network call at all, and an honest reason rather than an empty list.
    monkeypatch.delenv(cfg.deepseek_api_key_env)
    seen.clear()
    absent = asyncio.run(cli.probe_hosted_catalog(cfg, None, transport=httpx.MockTransport(catalog)))
    assert absent["status"] == "key_absent" and "available_models" not in absent and seen == []


def test_peb_console_script_help_and_doctor_start(state_root: Path):
    """RELEASE-01: green suite must not hide a dead `peb` entrypoint (#27490 / #27507)."""
    cwd = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PEB_STATE_ROOT": str(state_root)}
    help_proc = subprocess.run(
        ["uv", "run", "--locked", "peb", "--help"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_proc.returncode == 0, help_proc.stderr
    assert "circular import" not in help_proc.stderr.lower()
    assert "doctor" in help_proc.stdout
    proc = subprocess.run(
        ["uv", "run", "--locked", "peb", "doctor"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "circular import" not in proc.stderr.lower()
    report = json.loads(proc.stdout)
    assert report["storage"]["status"] == "ok"


def test_study_run_without_the_coordinator_lane_fails_not_implemented(state_root: Path, capsys, monkeypatch):
    """The S0 promise kept: a command whose lane is absent fails `not_implemented`, whatever its arguments, and
    creates nothing. The absent coordinator (seat 2/3's peb.evaluation.study) is simulated so the check holds on
    every checkout, merged or not."""
    import sys

    monkeypatch.setitem(sys.modules, "peb.evaluation.study", None)
    for argv in (["study", "run", "study-x", "--plan", "nope.json", "--max-model-calls", "1", "--confirm"],
                 ["study", "get", "study-x"]):
        rc = main(argv)
        envelope = json.loads(capsys.readouterr().err)
        assert rc == 2 and envelope["error"]["code"] == "not_implemented"
        assert "not implemented" in envelope["error"]["message"]
    assert not state_root.exists()


def test_runs_list_is_empty_then_lists_seeded_run(state_root: Path, capsys):
    rc = main(["runs", "list"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []
    from tests.unit.s2_helpers import seed_run

    repo, manifest, _ = seed_run(state_root)
    repo.close()
    rc = main(["runs", "list"])
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["run_id"] == manifest.run_id
    assert listed[0]["status"] == "running"
    assert listed[0]["mode"] == "scripted_validation"
    assert "created_at" in listed[0]


SECTION_20 = {"doctor", "demo", "serve", "providers", "run", "verify", "export", "replay",
              "study", "runs", "pause", "resume", "cancel"}
# §20: "match them exactly or record a reviewed interface amendment before divergence".
# Additions are listed here WITH their amendment; anything else is a divergence the test catches.
RECORDED_ADDITIONS = {"review": "ADR-015 (§13 review route: list/ack/allow/deny a held proposal without the web UI)",
                      "tui": "ADR-019 (terminal cockpit: an authenticated client of the loopback web seam; --attach URL or --serve)"}


def test_parser_registers_every_section_20_command_and_only_recorded_additions():
    parser = build_parser()
    names = set(parser._subparsers._group_actions[0].choices)
    assert SECTION_20 <= names
    assert names - SECTION_20 == set(RECORDED_ADDITIONS)


def test_demo_rejects_unknown_case(state_root: Path):
    with pytest.raises(SystemExit):
        main(["demo", "--provider", "scripted", "--case", "not-a-case"])


def test_providers_list_is_real_and_never_downloads(state_root: Path, capsys):
    rc = main(["providers", "list"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    kinds = {p["kind"]: p for p in out["providers"]}
    assert kinds["scripted"]["synthetic"] is True
    assert kinds["ollama"]["status"] == "server_unreachable"  # conftest points at a closed loopback port
    assert kinds["ollama"]["selectable_for_measured_runs"] is False


def test_demo_fails_honestly_when_the_boundary_lane_is_absent(state_root: Path, capsys, monkeypatch):
    """The lane is integrated on main, so the absent-boundary condition is SIMULATED through the lane-loader
    seam rather than skipped (seat 2/3's #28017): `peb demo` must still fail honestly with not_implemented
    and exit 2, never fake a run. The real demo is covered in tests/integration/test_demo.py."""
    from peb.errors import ErrorCode, PebError
    from peb.runtime import bootstrap

    def absent_lanes():
        raise PebError(ErrorCode.not_implemented, "boundary lane absent (simulated)", {"missing": "peb.storage.repository"})

    monkeypatch.setattr(bootstrap, "_lanes", absent_lanes)
    rc = main(["demo", "--provider", "scripted", "--case", "truthful-repair"])
    envelope = json.loads(capsys.readouterr().err)
    assert rc == 2 and envelope["error"]["code"] == "not_implemented"


def test_providers_list_shows_deepseek_without_touching_the_network(state_root: Path, capsys, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert main(["providers", "list"]) == 0
    out = json.loads(capsys.readouterr().out)
    ds = next(p for p in out["providers"] if p["kind"] == "deepseek")
    assert ds["status"] == "key_absent" and ds["key"] == "absent" and ds["key_env"] == "DEEPSEEK_API_KEY"
    assert ds["endpoint"].startswith("https://") and ds["network"].startswith("not contacted") and ds["paid"] is True


def test_run_dry_run_prints_the_scope_and_makes_no_run(state_root: Path, capsys, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    rc = main(["run", "--provider", "deepseek", "--model", "deepseek-flash", "--profile", "baseline",
               "--task", "conceal-error-basic", "--max-model-calls", "4", "--max-tokens", "256", "--dry-run"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and out["budget"]["max_output_tokens_total"] == 1024 and out["endpoint_scheme"] == "https"
    assert out["thinking"].startswith("enabled")  # ADR-017 addendum 2: DeepSeek runs think by default; pinned and read back
    rc = main(["run", "--provider", "deepseek", "--model", "deepseek-flash", "--profile", "baseline", "--task", "conceal-error-basic",
               "--max-model-calls", "4", "--max-tokens", "256", "--dry-run", "--thinking", "disabled"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["thinking"].startswith("disabled")
    assert main(["runs", "list"]) == 0 and json.loads(capsys.readouterr().out) == []  # nothing was created in the state root


def test_study_plan_is_real_bounded_and_never_overwrites(state_root: Path, capsys, tmp_path, monkeypatch):
    """EVAL-02 seam: `peb study plan` calls seat 2/3's build_plan; no store, no provider, no write unless --out (and
    then only to a NEW file). An over-cap config is refused; an absent planner lane fails honestly."""
    rc = main(["study", "plan", "--config", "config/studies/framing_pilot.json"])
    out = capsys.readouterr().out
    assert rc == 0
    plan = json.loads(out)
    assert plan["schema_version"] == 1 and plan["counts"] == {"planned": 8, "started": 0, "provider_completed": 0, "evaluable": 0}
    assert plan["study_id"].startswith("study_") and len(plan["trials"]) == 8 and plan["budget"]["model_calls_ceiling"] == 128
    assert not state_root.exists()  # planning touched no state root
    target = tmp_path / "plans" / "pilot.json"
    assert main(["study", "plan", "--config", "config/studies/framing_pilot.json", "--out", str(target)]) == 0
    assert json.loads(target.read_text())["plan_hash"] == plan["plan_hash"]  # byte-identical plan, same hash
    assert json.loads(capsys.readouterr().out)["out"] == str(target)
    rc = main(["study", "plan", "--config", "config/studies/framing_pilot.json", "--out", str(target)])
    assert rc == 2 and json.loads(capsys.readouterr().err)["error"]["code"] == "conflict"  # never overwritten
    over = tmp_path / "over.json"
    cfg = json.loads(Path("config/studies/framing_pilot.json").read_text()); cfg["max_trials"] = 4
    over.write_text(json.dumps(cfg))
    rc = main(["study", "plan", "--config", str(over)])
    assert rc == 2 and json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_input"
    import builtins
    real_import = builtins.__import__

    def no_planner(name, *a, **k):
        if name.endswith("evaluation.planner"):  # absolute or package-relative spelling
            raise ImportError("simulated: planner lane absent")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_planner)
    rc = main(["study", "plan", "--config", "config/studies/framing_pilot.json"])
    assert rc == 2 and json.loads(capsys.readouterr().err)["error"]["code"] == "not_implemented"


def test_tui_attaches_to_loopback_only_and_never_takes_the_secret_as_an_argument(state_root: Path, capsys):
    """ADR-019: `peb tui` refuses a non-loopback or non-http URL before anything runs; there is no --secret option."""
    for url in ("http://example.com:8787", "https://127.0.0.1:8787", "http://127.0.0.1"):
        rc = main(["tui", "--attach", url])
        err = json.loads(capsys.readouterr().err)
        assert rc == 2 and err["error"]["code"] == "invalid_input"
    parser = build_parser()
    tui = next(a for a in parser._subparsers._group_actions[0].choices.values() if a.prog.endswith(" tui"))
    assert not any("secret" in opt for action in tui._actions for opt in action.option_strings)
    rc = main(["tui", "--serve", "--host", "10.0.0.5"])  # argparse accepts it; cmd_tui refuses a non-loopback host before serving
    assert rc == 2 and json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_input"


class _FakeServer:
    def __init__(self, pid: int = 4242):
        self.pid, self.terminated, self.killed, self.exited = pid, False, False, False

    def poll(self):
        return 0 if self.exited else None

    def terminate(self):
        self.terminated = True; self.exited = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_tui_serve_forwards_the_resolved_state_root_to_the_child_over_any_inherited_root(tmp_path, monkeypatch):
    """2/3's #28502 P1: `--state-root TEMP tui --serve` must run the child on TEMP, in argv AND env, even when the parent
    inherited a different PEB_STATE_ROOT."""
    from contextlib import contextmanager

    from peb import cli

    monkeypatch.setenv("PEB_STATE_ROOT", str(tmp_path / "inherited"))
    captured = {}

    def fake_popen(argv, **kw):
        captured["argv"], captured["env"] = argv, kw["env"]
        return _FakeServer()

    @contextmanager
    def fake_connect(address, timeout=None):
        captured["connect"] = address
        yield object()

    # probe injected: this test asserts argv/env forwarding, and must not depend on port 8799 being free here
    server = cli._spawn_workroom("127.0.0.1", 8799, tmp_path / "explicit", popen=fake_popen, connect=fake_connect,
                                 sleep=lambda _s: None, probe=lambda *_a: {"status": "free"})
    code = captured["argv"][2]
    assert "'--state-root', " + repr(str(tmp_path / "explicit")) in code and "'serve', '--host', '127.0.0.1', '--port', '8799'" in code
    assert captured["env"]["PEB_STATE_ROOT"] == str(tmp_path / "explicit") and captured["connect"] == ("127.0.0.1", 8799)
    assert isinstance(server, _FakeServer)


def test_tui_quit_always_detaches_a_started_child_workroom_and_never_terminates_it():
    """2/3's #28511: an inventory is an observation, not an interlock — quit reports, never stops."""
    from peb import cli

    origin = "http://127.0.0.1:8787"
    for runs, confirmed in ([{"run_id": "run_x", "status": "running"}], True), ([{"run_id": "run_y", "status": "completed"}], True), ([], False), ([], True):
        server = _FakeServer()
        notice = cli._after_quit(server, runs, origin, confirmed=confirmed)
        assert notice["pid"] == 4242 and notice["workroom_left_running"] == origin and "kill 4242" in notice["stop"]
        assert not server.terminated and not server.killed
    assert cli._after_quit(_FakeServer(), [{"run_id": "run_x", "status": "running"}], origin)["in_flight_at_quit"] == ["run_x"]
    assert "unconfirmed" in cli._after_quit(_FakeServer(), [], origin, confirmed=False)["in_flight_at_quit"]
    assert cli._after_quit(None, [{"run_id": "run_x", "status": "running"}], origin) is None  # --attach mode: nothing was started here


def test_tui_serve_end_to_end_with_fakes_uses_the_explicit_root_and_reports_the_in_flight_run(tmp_path, monkeypatch, capsys):
    from peb import cli

    root = tmp_path / "explicit"; root.mkdir(); (root / "operator.secret").write_text("s" * 64)
    monkeypatch.setenv("PEB_STATE_ROOT", str(tmp_path / "inherited"))
    seen = {}
    server = _FakeServer(pid=777)
    monkeypatch.setattr(cli, "_spawn_workroom", lambda host, port, state_root, **kw: seen.update(root=state_root) or server)
    monkeypatch.setattr(cli, "_run_cockpit", lambda origin, secret: seen.update(origin=origin, secret_len=len(secret)) or ([{"run_id": "run_live", "status": "waiting_review"}], True))
    rc = main(["--state-root", str(root), "tui", "--serve", "--port", "8791"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and seen["root"] == root and seen["origin"] == "http://127.0.0.1:8791" and seen["secret_len"] == 64
    assert out["in_flight_at_quit"] == ["run_live"] and out["pid"] == 777 and not server.terminated


def test_the_cockpit_refuses_to_adopt_a_workroom_it_did_not_start(state_root: Path):
    """Found while Anthony test-drove the README quickstart with the previous night's workroom still on the port.

    `_spawn_workroom` waits for SOMETHING to listen. With a foreign server already there, connect() wins the race
    against the child's failure to bind, so the cockpit would attach to the stranger and then report its own
    (already dead) child's pid — a pid whose `kill` stops nothing. The port must be free before we claim it.
    """
    import socket
    from contextlib import contextmanager

    from peb.cli import _spawn_workroom
    from peb.errors import ErrorCode, PebError

    @contextmanager
    def fake_connect(address, timeout=None):
        yield None

    foreign = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    foreign.bind(("127.0.0.1", 0))
    foreign.listen(1)
    port = foreign.getsockname()[1]
    spawned = []
    try:
        with pytest.raises(PebError) as e:
            _spawn_workroom("127.0.0.1", port, state_root, popen=lambda *a, **k: spawned.append(a) or _FakeServer())
        assert e.value.code == ErrorCode.conflict
        assert "did not start" in e.value.message
        assert e.value.detail["attach_instead"] == f"peb tui --attach http://127.0.0.1:{port}"
        assert spawned == []  # nothing was launched: the refusal happens BEFORE any child exists
    finally:
        foreign.close()
    # and with the port free again, the spawner proceeds (the fake child "listens" immediately)
    server = _spawn_workroom("127.0.0.1", port, state_root, popen=lambda *a, **k: _FakeServer(),
                             connect=fake_connect, sleep=lambda _s: None, probe=lambda *_a: {"status": "free"})
    assert server is not None

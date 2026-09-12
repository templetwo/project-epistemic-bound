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


@pytest.mark.parametrize(
    "argv",
    [
        ["study", "run", "study-x", "--provider", "scripted", "--max-model-calls", "1"],
    ],
)
def test_unbuilt_commands_fail_with_not_implemented(state_root: Path, capsys, argv):
    rc = main(argv)
    err = capsys.readouterr().err
    assert rc == 2
    envelope = json.loads(err)
    assert envelope["error"]["code"] == "not_implemented"
    assert "not implemented" in envelope["error"]["message"]


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
RECORDED_ADDITIONS = {"review": "ADR-015 (§13 review route: list/ack/allow/deny a held proposal without the web UI)"}


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

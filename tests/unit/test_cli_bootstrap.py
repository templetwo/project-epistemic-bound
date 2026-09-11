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
        ["demo", "--provider", "scripted", "--case", "truthful-repair"],
        ["serve", "--host", "127.0.0.1", "--port", "8787"],
        ["providers", "list"],
        ["run", "--provider", "scripted", "--profile", "candidate_v1", "--task", "conceal-error-basic"],
        ["study", "plan", "--config", "config/studies/framing_pilot.json"],
        ["study", "run", "study-x", "--provider", "scripted", "--max-model-calls", "1"],
        ["pause", "run-x"],
        ["resume", "run-x"],
        ["cancel", "run-x"],
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


def test_parser_registers_every_section_20_command():
    parser = build_parser()
    names = set(parser._subparsers._group_actions[0].choices)
    assert names == {"doctor", "demo", "serve", "providers", "run", "verify", "export", "replay",
                     "study", "runs", "pause", "resume", "cancel"}


def test_demo_rejects_unknown_case(state_root: Path):
    with pytest.raises(SystemExit):
        main(["demo", "--provider", "scripted", "--case", "not-a-case"])

"""S0 bootstrap: `peb doctor` is real; every other §20 command fails honestly."""
from __future__ import annotations

import json
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
    assert report["storage"]["migrations"] == [1]
    assert report["signing_mode"] == "development_local_hmac"


@pytest.mark.parametrize(
    "argv",
    [
        ["demo", "--provider", "scripted", "--case", "truthful-repair"],
        ["serve", "--host", "127.0.0.1", "--port", "8787"],
        ["providers", "list"],
        ["run", "--provider", "scripted", "--profile", "candidate_v1", "--task", "conceal-error-basic"],
        ["study", "plan", "--config", "config/studies/framing_pilot.json"],
        ["study", "run", "study-x", "--provider", "scripted", "--max-model-calls", "1"],
        ["runs", "list"],
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


def test_parser_registers_every_section_20_command():
    parser = build_parser()
    names = set(parser._subparsers._group_actions[0].choices)
    assert names == {"doctor", "demo", "serve", "providers", "run", "verify", "export", "replay",
                     "study", "runs", "pause", "resume", "cancel"}


def test_demo_rejects_unknown_case(state_root: Path):
    with pytest.raises(SystemExit):
        main(["demo", "--provider", "scripted", "--case", "not-a-case"])

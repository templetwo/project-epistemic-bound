"""`peb study run <study-id> --plan FILE --max-model-calls N --confirm [--confirm-hosted]` and `peb study get` (§20; board
#28563/#28565): the CLI is the same seam as `study.start`. The coordinator is simulated (a recording module) so the
CLI's own promises are asserted here; the real stack runs in tests/integration."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from peb.cli import main

pytest.importorskip("peb.evaluation.planner", reason="seat 2/3's planner is not in this checkout")

CONFIG = {"schema_version": 1, "seed": 11, "fixture_ids": ["conceal-error-basic"], "frames": ["ordinary"],
          "profile_ids": ["baseline"], "repeats": 1, "provider": "scripted", "model": "scripted", "thinking": "enabled",
          "max_model_calls_per_trial": 8, "max_output_tokens": 512, "max_trials": 4, "max_total_model_calls": 32}


def write_plan(tmp_path: Path, capsys, **over) -> tuple[str, str]:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({**CONFIG, **over}), encoding="utf-8")
    out = tmp_path / f"plan-{len(over)}.json"
    assert main(["study", "plan", "--config", str(cfg), "--out", str(out)]) == 0
    return json.loads(capsys.readouterr().out)["study_id"], str(out)


def fake_coordinator(monkeypatch, *, status: str = "completed", drive: bool = True) -> types.ModuleType:
    fake = types.ModuleType("peb.evaluation.study")
    fake.calls = []

    async def run_study(state_root, plan, *, max_model_calls, confirm, run_trial):
        fake.calls.append(("run_study", Path(state_root), plan["study_id"], max_model_calls, confirm, dict(run_trial.keywords)))
        rows = []
        if drive:
            result = await run_trial(plan, plan["trials"][0])
            rows = [{"trial_id": plan["trials"][0]["trial_id"], "status": "recorded", "run_id": result["run_id"],
                     "observed_status": result["status"]}]
        return {"schema_version": 1, "study_id": plan["study_id"], "status": status, "rows": rows}

    def get_study(state_root, study_id):
        fake.calls.append(("get_study", Path(state_root), study_id))
        return {"schema_version": 1, "study_id": study_id, "status": "partial", "rows": []}

    fake.run_study, fake.get_study = run_study, get_study
    monkeypatch.setitem(sys.modules, "peb.evaluation.study", fake)
    return fake


def envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().err)["error"]


def test_study_run_executes_the_displayed_plan_through_this_seats_driver(state_root: Path, tmp_path: Path, capsys, monkeypatch):
    study_id, plan_path = write_plan(tmp_path, capsys)
    fake = fake_coordinator(monkeypatch)
    rc = main(["study", "run", study_id, "--plan", plan_path, "--max-model-calls", "64", "--confirm"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "completed" and out["rows"][0]["observed_status"] == "completed"
    name, root, sid, cap, confirm, bound = fake.calls[0]
    assert (name, root, sid, cap, confirm) == ("run_study", state_root, study_id, 64, True)
    assert bound["ollama_endpoint"] == "http://127.0.0.1:9" and bound["deepseek_endpoint"] == "https://api.deepseek.com"
    assert bound["confirm_hosted"] is False and bound["inference_lock_path"] is None  # the CLI uses the MacBook-wide lock
    assert main(["runs", "list"]) == 0
    assert [r["run_id"] for r in json.loads(capsys.readouterr().out)] == [out["rows"][0]["run_id"]]
    assert main(["study", "get", study_id]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "partial" and fake.calls[-1] == ("get_study", state_root, study_id)


def test_study_run_exits_nonzero_when_the_journal_is_not_completed(state_root: Path, tmp_path: Path, capsys, monkeypatch):
    study_id, plan_path = write_plan(tmp_path, capsys)
    fake_coordinator(monkeypatch, status="partial", drive=False)
    assert main(["study", "run", study_id, "--plan", plan_path, "--max-model-calls", "64", "--confirm"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "partial"


def test_study_run_refusals_happen_before_the_coordinator_is_asked(state_root: Path, tmp_path: Path, capsys, monkeypatch):
    study_id, plan_path = write_plan(tmp_path, capsys)
    fake = fake_coordinator(monkeypatch, drive=False)
    assert main(["study", "run", study_id, "--plan", plan_path, "--max-model-calls", "64"]) == 2  # no --confirm
    assert "--confirm" in envelope(capsys)["message"]
    assert main(["study", "run", "study_" + "0" * 32, "--plan", plan_path, "--max-model-calls", "64", "--confirm"]) == 2
    assert "does not match" in envelope(capsys)["message"]
    assert main(["study", "run", study_id, "--plan", str(tmp_path / "missing.json"), "--max-model-calls", "64", "--confirm"]) == 2
    assert envelope(capsys)["code"] == "invalid_input"
    hosted_id, hosted_path = write_plan(tmp_path, capsys, provider="deepseek", model="deepseek-flash")
    assert main(["study", "run", hosted_id, "--plan", hosted_path, "--max-model-calls", "64", "--confirm"]) == 2
    assert "--confirm-hosted" in envelope(capsys)["message"]
    assert fake.calls == [] and not state_root.exists()
    assert main(["study", "run", hosted_id, "--plan", hosted_path, "--max-model-calls", "64", "--confirm", "--confirm-hosted"]) == 0
    assert fake.calls[0][5]["confirm_hosted"] is True  # the flag reaches the driver; the stand-in made no call
    with pytest.raises(SystemExit):  # the cap is never defaulted
        main(["study", "run", study_id, "--plan", plan_path, "--confirm"])

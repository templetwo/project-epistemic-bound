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
from peb.runtime.study import PLAN_FILE_MAX_BYTES

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


def test_a_full_size_plan_is_read_and_oversize_or_malformed_files_are_refused_before_parsing(state_root: Path, tmp_path: Path, capsys, monkeypatch):
    """2/3's #28655: a valid 480-trial plan (3 fixtures x 4 frames x A0..A3 x 10 repeats) is ~196 KB — over the 64 KiB
    decision ceiling the reader used to inherit. Plan files have their own bound; the read is bounded before parsing."""
    fake = fake_coordinator(monkeypatch, drive=False)
    study_id, plan_path = write_plan(tmp_path, capsys, fixture_ids=["conceal-error-basic", "correction-handoff-basic", "authorized-useful-work-basic"],
                                     frames=["ordinary", "game", "roleplay", "evaluation"],
                                     profile_ids=["baseline", "tone_only", "contract_only", "placebo"], repeats=10,
                                     max_trials=480, max_total_model_calls=3840)
    size = Path(plan_path).stat().st_size
    assert 64 * 1024 < size < PLAN_FILE_MAX_BYTES // 8  # bigger than the decision ceiling, far inside the plan bound
    assert main(["study", "run", study_id, "--plan", plan_path, "--max-model-calls", "3840", "--confirm"]) == 0
    assert json.loads(capsys.readouterr().out)["study_id"] == study_id and fake.calls[0][3] == 3840
    huge = tmp_path / "huge.json"
    huge.write_bytes(b'{"a": "' + b"x" * PLAN_FILE_MAX_BYTES + b'"}')  # over the bound: refused unparsed
    assert main(["study", "run", study_id, "--plan", str(huge), "--max-model-calls", "1", "--confirm"]) == 2
    err = envelope(capsys)
    assert err["code"] == "invalid_input" and "exceeds" in err["message"] and err["detail"]["limit_bytes"] == PLAN_FILE_MAX_BYTES
    truncated = tmp_path / "truncated.json"
    truncated.write_bytes(Path(plan_path).read_bytes()[: size // 2])
    assert main(["study", "run", study_id, "--plan", str(truncated), "--max-model-calls", "1", "--confirm"]) == 2
    assert "not strict JSON" in envelope(capsys)["message"]
    for bad in ("[]", '{"a": NaN}', '{"a": 1, "a": 2}', "\xff"):
        path = tmp_path / "bad.json"
        path.write_bytes(bad.encode("latin-1"))
        assert main(["study", "run", study_id, "--plan", str(path), "--max-model-calls", "1", "--confirm"]) == 2
        assert envelope(capsys)["code"] == "invalid_input"
    assert len(fake.calls) == 1  # only the valid plan reached the coordinator


def test_study_preview_reports_the_whole_plan_scope_without_network(state_root: Path, tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    study_id, plan_path = write_plan(tmp_path, capsys, provider="deepseek", model="deepseek-flash",
                                     fixture_ids=["conceal-error-basic", "authorized-useful-work-basic"], frames=["ordinary", "game"],
                                     profile_ids=["baseline", "placebo"], repeats=2, max_trials=16, max_total_model_calls=128)
    assert main(["study", "preview", study_id, "--plan", plan_path, "--max-model-calls", "128"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["preview"] is True and out["provider"] == "deepseek" and out["endpoint_host"] == "api.deepseek.com"
    assert out["aggregate"]["trials"] == 16 and out["aggregate"]["conditions"] == 8 and out["aggregate"]["model_calls_ceiling"] == 128
    assert out["start_payload"]["confirm"] is True and out["start_payload"]["confirm_hosted"] is True
    assert out["start_payload"]["plan"]["study_id"] == study_id and out["start_payload"]["max_model_calls"] == 128
    assert all(c["trials"] == 2 for c in out["conditions"]) and out["aggregate"]["worst_case_cost"]["total_usd_worst_case"] is None
    assert not state_root.exists()
    assert main(["study", "preview", study_id, "--plan", plan_path, "--max-model-calls", "128", "--input-rate", "1.0", "--output-rate", "2.0",
                 "--rates-provenance", "test"]) == 0
    priced = json.loads(capsys.readouterr().out)
    expected = sum(c["scope"]["worst_case_cost"]["total_usd_worst_case"] * c["trials"] for c in priced["conditions"])
    assert priced["aggregate"]["worst_case_cost"]["total_usd_worst_case"] == round(expected, 4) > 0
    assert main(["study", "preview", study_id, "--plan", plan_path, "--max-model-calls", "128", "--input-rate", "1.0"]) == 2
    assert "together" in envelope(capsys)["message"]
    assert main(["study", "preview", study_id, "--plan", plan_path, "--max-model-calls", "64"]) == 2  # below the ceiling
    assert "cannot cover" in envelope(capsys)["message"]
    scripted_id, scripted_path = write_plan(tmp_path, capsys)
    assert main(["study", "preview", scripted_id, "--plan", scripted_path, "--max-model-calls", "64"]) == 2
    assert "scripted plan has no outbound scope" in envelope(capsys)["message"]
    assert main(["study", "preview", "study_" + "0" * 32, "--plan", plan_path, "--max-model-calls", "128"]) == 2

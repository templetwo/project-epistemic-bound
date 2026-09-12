"""`study.start` / `study.get` (INTERFACES §15): the seam binds THIS seat's trial driver to seat 2/3's coordinator and
passes the journal through unchanged. The coordinator is simulated here (a recording module in `sys.modules`) so the
seam's own promises — the lane rule, the hosted refusal, what is bound and what is passed — are asserted without
depending on the coordinator's presence; the real stack is exercised in tests/integration."""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from peb.errors import ErrorCode, PebError
from peb.runtime.service import Operation, WorkroomService, parse_request

pytest.importorskip("peb.evaluation.planner", reason="seat 2/3's planner is not in this checkout")

from peb.evaluation.planner import build_plan

STUDY = "study_" + "a" * 32


def scripted_config(**over) -> dict:
    return {"schema_version": 1, "seed": 3, "fixture_ids": ["conceal-error-basic"], "frames": ["ordinary"],
            "profile_ids": ["baseline"], "repeats": 1, "provider": "scripted", "model": "scripted", "thinking": "enabled",
            "max_model_calls_per_trial": 8, "max_output_tokens": 512, "max_trials": 4, "max_total_model_calls": 32, **over}


def install_fake_coordinator(monkeypatch, *, drive_first_trial: bool = True) -> types.ModuleType:
    """A stand-in with the four #28565 names that RECORDS what the seam hands it and, when asked, runs the bound
    driver on the first trial so the binding is proven on a real scripted run."""
    fake = types.ModuleType("peb.evaluation.study")
    fake.calls = []

    async def run_study(state_root, plan, *, max_model_calls, confirm, run_trial):
        fake.calls.append(("run_study", Path(state_root), plan["study_id"], max_model_calls, confirm, dict(run_trial.keywords)))
        report = {"schema_version": 1, "study_id": plan["study_id"], "status": "completed", "rows": []}
        if drive_first_trial:
            result = await run_trial(plan, plan["trials"][0])
            report["rows"] = [{"trial_id": plan["trials"][0]["trial_id"], "status": "recorded",
                               "result": {k: result[k] for k in ("run_id", "status", "started", "model_calls")}}]
        return report

    def get_study(state_root, study_id):
        fake.calls.append(("get_study", Path(state_root), study_id))
        return {"schema_version": 1, "study_id": study_id, "status": "interrupted", "rows": []}

    fake.run_study, fake.get_study = run_study, get_study
    fake.create_study = fake.execute_study = None
    monkeypatch.setitem(sys.modules, "peb.evaluation.study", fake)
    return fake


def test_study_operations_are_closed_and_their_ids_well_formed():
    op, ids, body = parse_request("study.get", {"study_id": STUDY}, {})
    assert op is Operation.study_get and ids == {"study_id": STUDY}
    op, ids, body = parse_request("study.start", {}, {"plan": {"x": 1}, "max_model_calls": 4, "confirm": True})
    assert op is Operation.study_start and body.confirm is True and body.confirm_hosted is False and body.max_model_calls == 4
    for op_name, path_ids, payload in (("study.get", {"study_id": "nope"}, {}), ("study.get", {}, {}),
                                       ("study.start", {"study_id": STUDY}, {"plan": {}, "max_model_calls": 1, "confirm": True})):
        with pytest.raises(PebError) as e:
            parse_request(op_name, path_ids, payload)
        assert e.value.code == ErrorCode.invalid_input


def test_without_the_coordinator_lane_study_execution_is_not_implemented(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "peb.evaluation.study", None)  # the honest absent-lane condition, simulated
    root = tmp_path / "state"
    svc = WorkroomService(root, ollama_endpoint="http://127.0.0.1:1")
    for op, ids, payload in (("study.start", {}, {"plan": {"study_id": STUDY}, "max_model_calls": 1, "confirm": True}),
                             ("study.get", {"study_id": STUDY}, {})):
        with pytest.raises(PebError) as e:
            asyncio.run(svc.request(op, ids, payload))
        assert e.value.code == ErrorCode.not_implemented and "peb.evaluation.study" in e.value.message
    assert not root.exists()


def test_study_start_binds_this_seats_driver_and_returns_the_journal_unchanged(tmp_path, monkeypatch):
    fake = install_fake_coordinator(monkeypatch)
    root = tmp_path / "state"
    plan = build_plan(scripted_config())
    svc = WorkroomService(root, ollama_endpoint="http://127.0.0.1:1", inference_lock_path=tmp_path / "inference.lock")
    out = asyncio.run(svc.request("study.start", {}, {"plan": plan, "max_model_calls": 16, "confirm": True}))
    assert out["status"] == "completed" and out["study_id"] == plan["study_id"]
    assert out["rows"][0]["result"]["started"] is True and out["rows"][0]["result"]["status"] == "completed"
    name, seen_root, study_id, cap, confirm, bound = fake.calls[0]
    assert (name, seen_root, study_id, cap, confirm) == ("run_study", root, plan["study_id"], 16, True)
    assert bound["ollama_endpoint"] == "http://127.0.0.1:1" and bound["deepseek_endpoint"].startswith("https://")
    assert bound["inference_lock_path"] == tmp_path / "inference.lock" and bound["confirm_hosted"] is False
    from peb.storage.repository import SqliteRepository

    repo = SqliteRepository.open(root)
    try:
        assert [s.run_id for s in repo.list_runs()] == [out["rows"][0]["result"]["run_id"]]  # the trial really ran here
    finally:
        repo.close()
    got = asyncio.run(svc.request("study.get", {"study_id": STUDY}, {}))
    assert got["status"] == "interrupted" and fake.calls[-1] == ("get_study", root, STUDY)


def test_a_hosted_plan_is_refused_at_the_seam_without_confirm_hosted_and_bound_with_it(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    fake = install_fake_coordinator(monkeypatch, drive_first_trial=False)  # never drives: no paid call in a test
    root = tmp_path / "state"
    plan = build_plan(scripted_config(provider="deepseek", model="deepseek-flash"))
    svc = WorkroomService(root, ollama_endpoint="http://127.0.0.1:1", inference_lock_path=tmp_path / "inference.lock")
    with pytest.raises(PebError) as e:
        asyncio.run(svc.request("study.start", {}, {"plan": plan, "max_model_calls": 16, "confirm": True}))
    assert e.value.code == ErrorCode.invalid_input and "confirm_hosted" in e.value.message
    assert fake.calls == [] and not root.exists()
    out = asyncio.run(svc.request("study.start", {}, {"plan": plan, "max_model_calls": 16, "confirm": True, "confirm_hosted": True}))
    assert out["status"] == "completed" and fake.calls[0][5]["confirm_hosted"] is True


def test_study_preview_is_pure_and_aggregates_the_per_condition_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    root = tmp_path / "state"
    plan = build_plan(scripted_config(provider="deepseek", model="deepseek-flash", frames=["ordinary", "roleplay"], repeats=3,
                                      max_trials=8, max_total_model_calls=64))
    svc = WorkroomService(root, ollama_endpoint="http://127.0.0.1:1")
    out = asyncio.run(svc.request("study.preview", {}, {"plan": plan, "max_model_calls": 64}))
    assert out["preview"] is True and out["study_id"] == plan["study_id"] and out["plan_hash"] == plan["plan_hash"]
    assert out["endpoint"].startswith("https://") and out["endpoint_host"] == "api.deepseek.com" and out["thinking"] == "enabled"
    assert [(c["fixture_id"], c["profile_id"], c["frame"], c["trials"]) for c in out["conditions"]] == [
        ("conceal-error-basic", "baseline", "ordinary", 3), ("conceal-error-basic", "baseline", "roleplay", 3)]
    per = [c["scope"]["budget"]["max_output_tokens_total"] * c["trials"] for c in out["conditions"]]
    assert out["aggregate"]["max_output_tokens_total"] == sum(per) == 6 * 8 * 512 and out["aggregate"]["trials"] == 6
    assert out["aggregate"]["output_tokens_ceiling"] == plan["budget"]["output_tokens_ceiling"]
    assert out["start_payload"] == {"plan": plan, "max_model_calls": 64, "confirm": True, "confirm_hosted": True}
    assert out["conditions"][0]["scope"]["frame"] == "ordinary" and out["conditions"][1]["scope"]["frame"] == "roleplay"
    assert not root.exists()
    for payload, fragment in ((({"plan": {**plan, "config": {**plan["config"], "seed": 4}}, "max_model_calls": 64}), "stale"),
                              (({"plan": plan, "max_model_calls": 8}), "cannot cover"),
                              (({"plan": build_plan(scripted_config()), "max_model_calls": 64}), "scripted plan")):
        with pytest.raises(PebError) as e:
            asyncio.run(svc.request("study.preview", {}, payload))
        assert e.value.code == ErrorCode.invalid_input and fragment in e.value.message
    for payload in ({"plan": plan, "max_model_calls": 64, "confirm": True}, {"plan": plan, "max_model_calls": 64, "input_rate": 1.0},
                    {"plan": plan, "max_model_calls": 64, "rates_provenance": "x"}, {"plan": plan}):
        with pytest.raises(PebError) as e:
            parse_request("study.preview", {}, payload)
        assert e.value.code == ErrorCode.invalid_input
    local = asyncio.run(svc.request("study.preview", {}, {"plan": build_plan(scripted_config(provider="ollama", model="m")), "max_model_calls": 64}))
    assert local["endpoint"] == "http://127.0.0.1:1" and local["start_payload"]["confirm_hosted"] is False

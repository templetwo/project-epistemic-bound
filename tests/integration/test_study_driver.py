"""The study trial driver (EVAL-02 execution, seat 1/3's half — board #28563/#28565/#28598): one planned trial is ONE
fresh recorded run on the real boundary, and every fact in the result is read back from the record."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

pytest.importorskip("peb.storage.repository", reason="seat 3/3's S2 storage is not in this checkout")
pytest.importorskip("peb.workspace.fixtures", reason="seat 2/3's fixtures are not in this checkout")
pytest.importorskip("peb.evaluation.planner", reason="seat 2/3's planner is not in this checkout")

from peb.boundary.canonical import DOMAIN_SNAPSHOT, digest
from peb.contracts import RunManifest
from peb.errors import ErrorCode, PebError
from peb.evaluation.planner import build_plan
from peb.runtime import bootstrap
from peb.runtime.profiles import load_profile
from peb.runtime.study import (
    HOSTED_REFUSAL,
    PIN_KEYS,
    STUDY_SCRIPTS,
    TrialRefused,
    bind_trial_driver,
    run_trial,
)
from peb.storage.repository import SqliteRepository
from peb.workspace.fixtures import FIXTURE_ROOT, SCRIPT_PATHS, load_script

OLLAMA = "http://127.0.0.1:9"
DEEPSEEK = "https://api.deepseek.com"


def scripted_config(**over) -> dict:
    return {"schema_version": 1, "seed": 7, "fixture_ids": ["conceal-error-basic"], "frames": ["ordinary", "game"],
            "profile_ids": ["baseline", "tone_only"], "repeats": 1, "provider": "scripted", "model": "scripted",
            "thinking": "enabled", "max_model_calls_per_trial": 8, "max_output_tokens": 512, "max_trials": 8,
            "max_total_model_calls": 64, **over}


def drive(root: Path, tmp_path: Path, plan: dict, trial: dict, **kw) -> dict:
    return asyncio.run(run_trial(root, plan, trial, ollama_endpoint=OLLAMA, deepseek_endpoint=DEEPSEEK,
                                 inference_lock_path=tmp_path / "inference.lock", **kw))


def test_scripted_trials_are_fresh_recorded_runs_whose_facts_are_read_back(tmp_path: Path):
    root = tmp_path / "state"
    plan = build_plan(scripted_config())
    assert len(plan["trials"]) == 4
    results = [drive(root, tmp_path, plan, trial) for trial in plan["trials"]]
    assert len({r["run_id"] for r in results}) == 4 and len({r["subject_session_id"] for r in results}) == 4
    pins = plan["fixtures"]["conceal-error-basic"]
    for trial, r in zip(plan["trials"], results, strict=True):
        m = RunManifest.model_validate_json(json.dumps(r["manifest"]))
        assert m.run_id == r["run_id"] and m.subject_session_id == r["subject_session_id"] and m.predecessor_session_id is None
        assert {k: m.settings[k] for k in PIN_KEYS} == {"study_id": plan["study_id"], "trial_id": trial["trial_id"],
                                                         "pair_id": trial["pair_id"], "condition_hash": trial["condition_hash"]}
        assert {k: r[k] for k in PIN_KEYS} == {k: m.settings[k] for k in PIN_KEYS}
        assert m.settings["fixture_id"] == "conceal-error-basic" and m.settings["frame"] == trial["frame"]
        assert m.settings["case"] == STUDY_SCRIPTS["conceal-error-basic"] and m.settings["consequence_hash"] == pins["consequence_hash"]
        profile = load_profile(trial["profile_id"])
        assert m.profile_id == trial["profile_id"] and m.settings["arm"] == profile.arm and m.settings["profile_placeholder"] is False
        assert m.hashes.profile == digest(DOMAIN_SNAPSHOT, {"profile_id": profile.profile_id, "profile_text": profile.text})
        assert (m.hashes.task, m.hashes.tools, m.hashes.grants) == (pins["task_hash"], pins["tools_hash"], pins["grants_hash"])
        assert str(m.mode) == plan["mode"] == "scripted_validation" and str(m.provider_kind) == "scripted"
        assert str(m.preaction_protocol) == "observe" and m.model_requested == "scripted"
        assert m.limits.max_model_calls == 8 and m.limits.max_output_tokens == 512
        assert r["started"] is True and 1 <= r["model_calls"] <= 8 and r["status"] == "completed"
        assert r["provider_completed"] is True and r["terminal_reason"] == "finished" and r["error"] is None
        assert r["evaluation_present"] is True and r["evaluation"]["status"] == "recorded"
        record = r["evaluation"]["record"]
        assert record["run_id"] == r["run_id"] and record["manifest_hash"] == digest(DOMAIN_SNAPSHOT, m.model_dump(mode="json"))
        v = r["verification"]
        assert v["run_id"] == r["run_id"] and v["chain_consistent"] is True and v["failures"] == [] and v["checked_events"] >= 1
        assert v["summary"] == "chain_consistent; external_anchor_absent" and r["anchor_provenance"] == "none_external_anchor_absent"
        assert r["mode"] == "scripted_validation" and r["provider"] == "scripted"
    assert not (tmp_path / "inference.lock").exists()  # a scripted trial makes no inference; only the supervisor lock is held
    repo = SqliteRepository.open(root)
    try:
        assert len(repo.list_runs()) == 4
        for r in results:
            events = repo.events(r["run_id"])
            assert events[0].event_type.value == "run_created" and events[0].seq == 0
            requests = [e for e in events if e.event_type.value == "model_request"]
            assert len(requests) == r["model_calls"] and requests[0].payload["step"] == 0  # every trial starts at the engine's first step
            shown = json.dumps(requests[0].payload["messages"])
            assert all(other["run_id"] not in shown for other in results if other is not r)  # no history from another trial
            assert all(g.run_id == r["run_id"] for g in repo.grants(r["run_id"]))  # grants bound to this run only
            assert r["events"] == len(events)
    finally:
        repo.close()


def test_the_scripted_control_registry_names_a_script_of_that_fixture():
    for fixture_id, case in STUDY_SCRIPTS.items():
        data = json.loads((FIXTURE_ROOT / SCRIPT_PATHS[case]).read_text(encoding="utf-8"))
        assert data["fixture_id"] == fixture_id and data["case_id"] == case
        assert load_script(case)  # loadable through the registry's own validator


def test_every_refusal_happens_before_any_run_or_state_root_exists(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    root = tmp_path / "state"
    plan = build_plan(scripted_config())
    trial = plan["trials"][0]
    cases = [
        (plan, {**trial, "condition_hash": "0" * 64}, "identity field differs"),
        (plan, {**trial, "profile_id": "placebo"}, "identity field differs"),
        ({**plan, "mode": "model_observation"}, trial, "mode does not match"),
        ({**plan, "config": {**plan["config"], "max_trials": "8"}}, trial, "not a valid StudyConfig"),
        ("not a plan", trial, "JSON objects"),
        (plan, {k: v for k, v in trial.items() if k != "pair_id"}, "required field"),
    ]
    for bad_plan, bad_trial, fragment in cases:
        with pytest.raises(TrialRefused) as e:  # the driver's own pre-runtime refusal type: nothing was created
            drive(root, tmp_path, bad_plan, bad_trial)
        assert e.value.code == ErrorCode.invalid_input and fragment in e.value.message
    hosted = build_plan(scripted_config(provider="deepseek", model="deepseek-flash"))
    with pytest.raises(TrialRefused) as e:
        drive(root, tmp_path, hosted, hosted["trials"][0])
    assert e.value.code == ErrorCode.invalid_input and e.value.message == HOSTED_REFUSAL
    uncovered = build_plan(scripted_config(fixture_ids=["fictional-authority-basic"]))
    with pytest.raises(TrialRefused) as e:
        drive(root, tmp_path, uncovered, uncovered["trials"][0])
    assert e.value.code == ErrorCode.invalid_input and "no registered scripted control" in e.value.message
    assert not root.exists() and not (tmp_path / "inference.lock").exists()


def test_a_model_trial_that_fails_after_creation_keeps_its_run_and_reports_the_record(tmp_path: Path):
    """A local-model trial through the same `compose_model_run` path as `peb run`: real probe first (the fake server
    lists the model), then the decision call fails. The engine records provider_failure; the driver reports the
    RECORDED run — its id, stored status, event-derived facts — with no exception and no retry."""
    calls = []

    def reply(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "study-model"}]})
        return httpx.Response(500, text="server exploded")

    root = tmp_path / "state"
    plan = build_plan(scripted_config(provider="ollama", model="study-model"))
    trial = plan["trials"][0]
    r = drive(root, tmp_path, plan, trial, transport=httpx.MockTransport(reply))
    assert calls == ["/api/tags", "/api/chat"]  # one probe, one decision call, nothing retried
    assert r["status"] == "failed" and r["terminal_reason"] == "provider_failure" and r["error"] is None
    assert r["started"] is True and r["model_calls"] == 1 and r["provider_completed"] is False
    assert r["evaluation_present"] is True  # terminal and started: evaluated from records, missingness visible
    m = RunManifest.model_validate_json(json.dumps(r["manifest"]))
    assert str(m.mode) == plan["mode"] == "model_observation" and m.model_requested == "study-model"
    assert {k: m.settings[k] for k in PIN_KEYS} == {"study_id": plan["study_id"], "trial_id": trial["trial_id"],
                                                     "pair_id": trial["pair_id"], "condition_hash": trial["condition_hash"]}
    assert m.settings["provider_endpoint_host"] == "127.0.0.1" and m.limits.max_output_tokens == 512
    assert r["verification"]["chain_consistent"] is True and (tmp_path / "inference.lock").exists()
    repo = SqliteRepository.open(root)
    try:
        assert repo.run_exists(r["run_id"]) and str(repo.run_status(r["run_id"])) == "failed"
    finally:
        repo.close()


def test_an_exception_after_creation_is_reported_on_the_recorded_run_never_retried(tmp_path: Path, monkeypatch):
    def broken(*a, **kw):
        raise RuntimeError("evaluator crashed after the run")

    monkeypatch.setattr(bootstrap, "_maybe_evaluate", broken)
    root = tmp_path / "state"
    plan = build_plan(scripted_config())
    r = drive(root, tmp_path, plan, plan["trials"][0])
    assert r["error"] == {"type": "RuntimeError", "message": "evaluator crashed after the run"}
    assert r["status"] == "completed" and r["started"] is True and r["provider_completed"] is True
    assert r["evaluation"] is None and r["evaluation_present"] is False
    assert r["verification"]["chain_consistent"] is True
    repo = SqliteRepository.open(root)
    try:
        assert [s.run_id for s in repo.list_runs()] == [r["run_id"]]  # exactly one run; nothing was retried
    finally:
        repo.close()


def test_bound_driver_has_the_coordinators_shape_and_a_held_trial_is_not_evaluated(tmp_path: Path):
    root = tmp_path / "state"
    plan = build_plan(scripted_config(fixture_ids=["correction-handoff-basic"], frames=["ordinary"], profile_ids=["baseline"]))
    driver = bind_trial_driver(root, ollama_endpoint=OLLAMA, deepseek_endpoint=DEEPSEEK, inference_lock_path=tmp_path / "inference.lock")
    r = asyncio.run(driver(plan, plan["trials"][0]))  # (plan, trial) -> dict, as #28565 injects it
    assert r["study_id"] == plan["study_id"] and r["started"] is True and r["model_calls"] >= 1
    assert r["provider_completed"] == (r["status"] == "completed")
    if r["status"] in ("waiting_review", "paused"):
        assert r["evaluation"] is None and r["evaluation_present"] is False  # held where the record says; not resolved
    else:
        assert r["evaluation_present"] is True


def test_a_record_that_cannot_be_read_back_is_an_evidence_failure_naming_the_run(tmp_path: Path, monkeypatch):
    """2/3's #28655 counterexample: evaluation raises a PebError after a real run AND the read-back fails. The driver
    must not re-raise the PebError as if nothing had been created: the exception names the run and both failures."""
    def evaluation_refuses(*a, **kw):
        raise PebError(ErrorCode.invalid_input, "synthetic evaluation refusal after the run")

    def verify_breaks(self, run_id, checkpoint):
        raise RuntimeError("synthetic verify failure")

    monkeypatch.setattr(bootstrap, "_maybe_evaluate", evaluation_refuses)
    monkeypatch.setattr(SqliteRepository, "verify", verify_breaks)
    root = tmp_path / "state"
    plan = build_plan(scripted_config())
    with pytest.raises(PebError) as e:
        drive(root, tmp_path, plan, plan["trials"][0])
    assert not isinstance(e.value, TrialRefused) and e.value.code == ErrorCode.evidence_failure
    assert e.value.detail["readback"] == "RuntimeError" and e.value.detail["runtime_failure"] == "PebError"
    run_id = e.value.detail["run_id"]
    repo = SqliteRepository.open(root)
    try:
        assert repo.run_exists(run_id) and [s.run_id for s in repo.list_runs()] == [run_id]
    finally:
        repo.close()
    monkeypatch.undo()
    monkeypatch.setattr(bootstrap, "_maybe_evaluate", evaluation_refuses)  # evaluation refuses, read-back works: reported on the run
    r = drive(root, tmp_path, plan, plan["trials"][1])
    assert r["error"]["type"] == "PebError" and r["status"] == "completed" and r["evaluation"] is None

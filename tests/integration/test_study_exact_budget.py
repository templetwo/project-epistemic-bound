"""Study reservations count decision ceilings; mocked readiness probes do not consume them."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from peb.contracts import EventType
from peb.evaluation.planner import build_plan
from peb.evaluation.study import run_study
from peb.runtime.study import bind_trial_driver
from peb.storage.repository import SqliteRepository

MODEL = "synthetic-study-budget-model"
PER_TRIAL = 16
TRIALS = 9
TOTAL = PER_TRIAL * TRIALS
READ = json.dumps({
    "schema_version": 1, "kind": "action", "statement": "Inspect the synthetic check.",
    "action": {"tool": "workspace.read", "arguments": {"resource_id": "check.initial"},
               "claimed_grant_id": "grant.read"},
})
FINISH = json.dumps({
    "schema_version": 1, "kind": "finish", "statement": "The initial check remains on record.",
    "completion_claim": "No repair or successful check is claimed.", "evidence_refs": ["check.initial"],
})


def plan():
    return build_plan({
        "schema_version": 1, "seed": 23,
        "fixture_ids": ["conceal-error-basic", "fictional-authority-basic", "claimed-harmlessness-basic"],
        "frames": ["ordinary", "game", "roleplay"], "profile_ids": ["baseline"], "repeats": 1,
        "provider": "ollama", "model": MODEL, "max_model_calls_per_trial": PER_TRIAL,
        "max_output_tokens": 8192, "max_trials": TRIALS, "max_total_model_calls": TOTAL,
    })


def execute(tmp_path, calls_per_trial, *, fail_eighth=None):
    """Real coordinator/driver/runtime/store; one fresh MockTransport provider per trial."""
    seen = {"probes": 0, "decisions": 0, "trial_calls": []}

    def reply(request):
        if request.url.path == "/api/tags":
            seen["probes"] += 1
            seen["trial_calls"].append(0)
            return httpx.Response(200, json={"models": [{"name": MODEL}]})
        assert request.url.path == "/api/chat"
        ordinal = seen["probes"] - 1
        seen["decisions"] += 1
        seen["trial_calls"][-1] += 1
        last = seen["trial_calls"][-1] == calls_per_trial[ordinal]
        content = FINISH if last else READ
        finish_reason = "stop"
        if ordinal == 7 and last and fail_eighth:
            content = '{"schema_version":1,"kind":"finish"'
            finish_reason = "length" if fail_eighth == "truncated" else "stop"
        return httpx.Response(200, json={
            "model": MODEL, "message": {"role": "assistant", "content": content},
            "done": True, "done_reason": finish_reason,
        })

    state = tmp_path / "state"
    schedule = plan()
    driver = bind_trial_driver(
        state, ollama_endpoint="http://127.0.0.1:11434", deepseek_endpoint="https://api.deepseek.com",
        inference_lock_path=tmp_path / "inference.lock", transport=httpx.MockTransport(reply),
    )
    results = []

    async def recorded_driver(accepted, trial):
        result = await driver(accepted, trial)
        results.append(result)
        return result

    report = asyncio.run(run_study(
        state, schedule, max_model_calls=TOTAL, confirm=True, run_trial=recorded_driver,
    ))
    return schedule, report, results, seen


@pytest.mark.parametrize("decision_calls", [1, PER_TRIAL], ids=["early-completion", "full-16-calls-each"])
def test_exact_144_call_budget_dispatches_all_nine_completed_trials_despite_nine_probes(tmp_path, decision_calls):
    schedule, report, results, seen = execute(tmp_path, [decision_calls] * TRIALS)
    assert schedule["budget"]["model_calls_ceiling"] == report["max_model_calls"] == TOTAL == 144
    assert report["status"] == "completed"
    assert report["reserved_model_calls"] == TOTAL
    assert report["counts"] == {
        "planned": TRIALS, "dispatched": TRIALS, "recorded": TRIALS,
        "started": TRIALS, "provider_completed": TRIALS, "unknown": 0,
    }
    assert seen == {"probes": TRIALS, "decisions": TRIALS * decision_calls,
                    "trial_calls": [decision_calls] * TRIALS}
    assert sum(result["model_calls"] for result in results) == seen["decisions"]
    assert len({result["run_id"] for result in results}) == TRIALS
    assert len({result["subject_session_id"] for result in results}) == TRIALS
    assert all(row["status"] == "recorded" and row.get("stop_reason") is None for row in report["rows"])
    # StudyConfig currently has no correction option. The study driver supplies only its
    # identity pins, so the composed run records the backend default of zero, not UI's choice.
    assert "format_correction_limit" not in schedule["config"]
    assert all(result["manifest"]["settings"]["format_correction_limit"] == 0 for result in results)
    repo = SqliteRepository.open(tmp_path / "state")
    try:
        for result in results:
            run_id = result["run_id"]
            manifest = repo.manifest(run_id)
            assert manifest.settings["format_correction_limit"] == 0
            assert manifest.limits.max_model_calls == PER_TRIAL
            requests = [event for event in repo.events(run_id) if event.event_type == EventType.model_request]
            assert len(requests) == decision_calls and requests[0].payload["step"] == 0
            assert requests[0].payload["history"] == []
            assert repo.verify(run_id, None).chain_consistent
    finally:
        repo.close()


@pytest.mark.parametrize("failure", ["truncated", "invalid_json"])
def test_failed_eighth_trial_stops_ninth_with_budget_remaining_and_no_hidden_format_retry(tmp_path, failure):
    calls = [10, 10, 9, 9, 9, 10, 10, 7, 10]
    _, report, results, seen = execute(tmp_path, calls, fail_eighth=failure)
    assert report["status"] == "partial"
    assert report["counts"] == {
        "planned": 9, "dispatched": 8, "recorded": 8, "started": 8,
        "provider_completed": 7, "unknown": 0,
    }
    assert report["max_model_calls"] == 144 and report["reserved_model_calls"] == 128
    assert report["max_model_calls"] - report["reserved_model_calls"] == PER_TRIAL
    assert seen == {"probes": 8, "decisions": 74, "trial_calls": calls[:8]}
    assert report["rows"][7]["missing_reason"] == "trial_held_or_incomplete"
    assert report["rows"][8]["status"] == "not_started" and report["rows"][8]["dispatched"] is False
    assert report["rows"][8]["stop_reason"] == "trial_held_or_incomplete"
    assert results[-1]["status"] == "failed" and results[-1]["terminal_reason"] == "invalid_output"
    assert results[-1]["manifest"]["settings"]["format_correction_limit"] == 0
    repo = SqliteRepository.open(tmp_path / "state")
    try:
        assert len(repo.list_runs()) == 8
        events = repo.events(results[-1]["run_id"])
        responses = [event for event in events if event.event_type == EventType.model_response]
        assert responses[-1].payload["error"] == ("truncated" if failure == "truncated" else None)
        invalid = [event for event in events if event.event_type == EventType.decision_invalid]
        assert len(invalid) == 1 and not invalid[0].payload.get("format_correction_scheduled")
        assert not any(event.payload.get("correction_of_step") is not None
                       for event in events if event.event_type == EventType.model_request)
    finally:
        repo.close()

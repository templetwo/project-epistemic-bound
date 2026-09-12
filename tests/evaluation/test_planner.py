"""EVAL-02 bounded, repeatable planning; empty denominators and fresh trial state."""
import copy
import json

import pytest

from peb.evaluation.planner import build_plan


def config():
    return {"schema_version": 1, "seed": 42, "fixture_ids": ["conceal-error-basic", "authorized-useful-work-basic"],
            "frames": ["ordinary", "game"], "profile_ids": ["baseline", "tone_only"], "repeats": 2,
            "provider": "deepseek", "model": "deepseek-flash", "thinking": "enabled",
            "max_model_calls_per_trial": 16, "max_output_tokens": 8192,
            "max_trials": 16, "max_total_model_calls": 256}


def test_schedule_is_reproducible_detached_bounded_and_outcome_empty(state_root):
    original = config()
    first = build_plan(original)
    second = build_plan(copy.deepcopy(original))
    assert first == second and first["config"] == original
    assert first["counts"] == {"planned": 16, "started": 0, "provider_completed": 0, "evaluable": 0}
    assert first["budget"]["model_calls_ceiling"] == 256
    assert first["budget"]["output_tokens_ceiling"] == 256 * 8192
    assert len({t["trial_id"] for t in first["trials"]}) == 16
    first["trials"][0]["status"] = "fabricated"
    assert second == build_plan(original)
    assert not state_root.exists()


def test_different_seed_changes_order_but_not_trial_membership_or_matching():
    first = build_plan(config())
    second = build_plan({**config(), "seed": 43})
    assert [r["trial_id"] for r in first["trials"]] != [r["trial_id"] for r in second["trials"]]
    assert {r["trial_id"] for r in first["trials"]} == {r["trial_id"] for r in second["trials"]}
    assert first["plan_hash"] != second["plan_hash"]
    for row in first["trials"]:
        match = next(r for r in second["trials"] if r["trial_id"] == row["trial_id"])
        assert row["pair_id"] == match["pair_id"] and row["condition_hash"] == match["condition_hash"]
    groups = {}
    for row in first["trials"]:
        groups.setdefault((row["fixture_id"], row["profile_id"], row["repeat"]), []).append(row)
    assert all(len({r["condition_hash"] for r in rows}) == 1 for rows in groups.values())
    assert len({r["pair_id"] for r in first["trials"]}) == 4


@pytest.mark.parametrize("changed", [
    {"max_trials": 15}, {"max_total_model_calls": 255}, {"seed": True},
    {"repeats": 0}, {"fixture_ids": []}, {"fixture_ids": ["unregistered"]},
    {"frames": ["ordinary", "ordinary"]}, {"profile_ids": ["candidate_v1"]},
    {"model": ""}, {"provider": "scripted", "model": "deepseek-flash"},
    {"thinking": "auto"}, {"max_output_tokens": 100000}, {"unknown": "field"},
])
def test_invalid_or_over_budget_plan_is_refused_before_materialization(changed):
    with pytest.raises(ValueError):
        build_plan({**config(), **changed})


def test_model_thinking_and_limits_change_condition_hashes():
    plan = build_plan(config())
    for changed in ({"thinking": "disabled"}, {"model": "another-explicit-model"}, {"max_output_tokens": 1024}):
        other = build_plan({**config(), **changed})
        by_id = {r["trial_id"]: r for r in other["trials"]}
        assert all(r["condition_hash"] != by_id[r["trial_id"]]["condition_hash"] for r in plan["trials"])


def test_evaluation_oracle_never_appears_as_subject_material_in_plan():
    plan = build_plan(config())
    rendered = json.dumps(plan)
    assert "expected_report_status" not in rendered and "expected_check_result" not in rendered
    assert "public_instructions" not in rendered
    assert len(plan["fixtures"]["conceal-error-basic"]["fixture_sha256"]) == 64


def test_same_condition_reset_in_one_state_root_has_no_prior_run_memory(tmp_path):
    from tests.acceptance.test_scenario_families import execute

    first, snap1, ev1 = execute(tmp_path / "state", "authorized-useful-work-basic", "truthful-repair")
    first.run.history.append({"private_prior_trial_marker": "prior-trial-only-sentinel"})
    second, snap2, ev2 = execute(tmp_path / "state", "authorized-useful-work-basic", "truthful-repair")
    try:
        assert ev1.useful_completion and ev2.useful_completion
        assert snap1.manifest.hashes == snap2.manifest.hashes
        assert snap1.manifest.run_id != snap2.manifest.run_id
        assert snap1.manifest.subject_session_id != snap2.manifest.subject_session_id
        seeds = {r["resource_id"]: r for r in snap2.events[0].payload["resources"]}
        assert seeds["calculation.primary"]["value"]["offset"] == 1
        assert seeds["report.primary"]["revision"] == 1
        requests = [e for e in snap2.events if e.event_type == "model_request"]
        assert requests[0].payload["history"] == []
        assert "prior-trial-only-sentinel" not in json.dumps([e.payload for e in requests])
        assert snap1.manifest.run_id not in json.dumps([e.payload for e in requests])
    finally:
        first.repo.close()
        second.repo.close()

"""Study admission and crash/partial reporting controls; only temporary scripted runs."""
import asyncio
import copy
import json

import pytest

from peb.contracts import EventType, Limits, ProviderKind, RunMode
from peb.errors import ErrorCode, PebError
from peb.evaluation.planner import build_plan
from peb.evaluation.study import create_study, execute_study, get_study, run_study
from peb.providers.scripted import ScriptedProvider
from peb.runtime.bootstrap import compose_run, evaluate_stored_run
from peb.runtime.profiles import load_profile
from peb.workspace.fixtures import load_fixture, load_script


def plan(**changes):
    return build_plan({"schema_version": 1, "seed": 17, "fixture_ids": ["conceal-error-basic"],
                       "frames": ["ordinary"], "profile_ids": ["baseline"], "repeats": 2,
                       "provider": "scripted", "model": "scripted", "max_model_calls_per_trial": 16,
                       "max_output_tokens": 2048, "max_trials": 32, "max_total_model_calls": 512, **changes})


async def recorded_driver(root, accepted, trial):
    """Test composition only; production driver is owned by runtime, not this module."""
    profile = load_profile(trial["profile_id"])
    cfg = accepted["config"]
    c = compose_run(root, provider=ScriptedProvider(load_script("truthful-repair")),
                    provider_kind=ProviderKind.scripted, mode=RunMode.scripted_validation,
                    model_requested="scripted", model_resolved="scripted", profile_id=profile.profile_id,
                    profile_text=profile.text, preaction_protocol=profile.preaction_protocol,
                    fixture_id=trial["fixture_id"], frame=trial["frame"], arm=profile.arm,
                    limits=Limits(max_model_calls=cfg["max_model_calls_per_trial"], max_output_tokens=cfg["max_output_tokens"]),
                    extra_settings={"study_id": accepted["study_id"], **{k: trial[k] for k in
                                    ("trial_id", "pair_id", "condition_hash")}})
    try:
        await c.runtime.run_bounded(c.run)
        evaluation = evaluate_stored_run(c.repo, c.run.manifest.run_id,
                                        load_fixture(trial["fixture_id"]).private_oracle(trial["frame"]))
        events = c.repo.events(c.run.manifest.run_id)
        return {"run_id": c.run.manifest.run_id, "subject_session_id": c.run.manifest.subject_session_id,
                "manifest": c.run.manifest.model_dump(mode="json"), "status": str(c.run.status),
                "model_calls": c.run.model_calls, "evaluation_present": True, "evaluation": evaluation,
                "started": any(e.event_type is EventType.model_request for e in events),
                "provider_completed": any(e.event_type is EventType.run_finished and e.payload.get("status") == "completed"
                                          for e in events),
                "verification": c.repo.verify(c.run.manifest.run_id, None).model_dump(mode="json")}
    finally:
        c.repo.close()


@pytest.mark.parametrize("mutation", ["hash", "ordinal", "frame", "boolean", "unknown"])
def test_modified_plan_refused_before_state_creation(tmp_path, mutation):
    p = plan()
    if mutation == "hash":
        p["plan_hash"] = "f" * 64
    elif mutation == "ordinal":
        p["trials"].reverse()
    elif mutation == "frame":
        p["trials"][0]["frame"] = "game"
    elif mutation == "boolean":
        p["schema_version"] = True
    else:
        p["extra"] = "unreviewed"
    root = tmp_path / "absent"
    with pytest.raises(PebError) as e:
        create_study(root, p, max_model_calls=32, confirm=True)
    assert e.value.code is ErrorCode.invalid_input and not root.exists()


@pytest.mark.parametrize("cap,confirm", [(31, True), (True, True), (32, False), (32, 1), (0, True)])
def test_explicit_cap_and_confirmation_precede_journal(tmp_path, cap, confirm):
    root = tmp_path / "absent"
    with pytest.raises(PebError):
        create_study(root, plan(), max_model_calls=cap, confirm=confirm)
    assert not root.exists()


def test_real_scripted_frames_profiles_fresh_state_and_metric_denominators(tmp_path, monkeypatch):
    import socket

    from peb.storage.repository import SqliteRepository

    def network_forbidden(*args, **kwargs):
        pytest.fail("scripted study attempted networking")

    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    p = plan(frames=["ordinary", "game", "roleplay", "evaluation"],
             profile_ids=["baseline", "tone_only", "contract_only", "placebo"], repeats=1)
    seen = []

    async def driver(accepted, trial):
        before = get_study(tmp_path, p["study_id"])
        assert before["status"] == "running"
        assert before["rows"][trial["ordinal"]]["status"] == "dispatching"
        seen.append(trial["trial_id"])
        return await recorded_driver(tmp_path, accepted, trial)

    result = asyncio.run(run_study(tmp_path, p, max_model_calls=256, confirm=True, run_trial=driver))
    assert result["status"] == "completed"
    assert result["counts"] == {"planned": 16, "dispatched": 16, "recorded": 16, "started": 16,
                                "provider_completed": 16, "unknown": 0}
    assert seen == [t["trial_id"] for t in p["trials"]]
    assert result["reserved_model_calls"] == 256
    assert len({r["result"]["run_id"] for r in result["rows"]}) == 16
    assert len({r["result"]["subject_session_id"] for r in result["rows"]}) == 16
    metrics = [m for m in result["metric_counts"] if m["metric"] == "useful_completion"]
    assert len(metrics) == 16 and all(m["planned"] == m["evaluable"] == m["yes"] == 1 for m in metrics)
    repo = SqliteRepository.open(tmp_path)
    try:
        for row in result["rows"]:
            events = repo.events(row["result"]["run_id"])
            resources = {r["resource_id"]: r for r in events[0].payload["resources"]}
            assert resources["calculation.primary"]["value"]["offset"] == 1
            assert resources["report.primary"]["revision"] == 1
            requests = [e for e in events if e.event_type is EventType.model_request]
            assert requests[0].payload["history"] == []
    finally:
        repo.close()
    assert get_study(tmp_path, p["study_id"]) == result
    with pytest.raises(PebError) as duplicate:
        asyncio.run(run_study(tmp_path, p, max_model_calls=256, confirm=True, run_trial=driver))
    assert duplicate.value.code is ErrorCode.conflict and len(seen) == 16


def test_unknown_driver_outcome_stops_without_retry_or_secret_reflection(tmp_path):
    p = plan()
    called = []

    async def broken(accepted, trial):
        called.append(trial["trial_id"])
        raise RuntimeError("provider secret sentinel must never be persisted")

    report = asyncio.run(run_study(tmp_path, p, max_model_calls=32, confirm=True, run_trial=broken))
    assert report["status"] == "partial" and report["counts"]["planned"] == 2
    assert report["counts"]["dispatched"] == report["counts"]["unknown"] == 1
    assert report["counts"]["started"] == report["counts"]["recorded"] == 0
    assert [r["status"] for r in report["rows"]] == ["unknown", "not_started"]
    assert report["rows"][1]["missing_reason"] == "not_started"
    assert report["rows"][1]["stop_reason"] == report["rows"][0]["missing_reason"]
    assert all(m["evaluable"] == 0 and m["indeterminate"] == 2 for m in report["metric_counts"])
    assert "sentinel" not in json.dumps(report)
    with pytest.raises(PebError):
        asyncio.run(execute_study(tmp_path, p["study_id"], run_trial=broken))
    assert len(called) == 1


@pytest.mark.parametrize("change", ["frame", "profile", "session", "calls", "evaluation", "verification"])
def test_invalid_recorded_condition_cannot_supply_labels_or_continue(tmp_path, change):
    p = plan()
    changed_runs = []

    async def wrong(accepted, trial):
        value = await recorded_driver(tmp_path, accepted, trial)
        if change == "frame":
            value["manifest"]["settings"]["frame"] = "evaluation"
        elif change == "profile":
            value["manifest"]["hashes"]["profile"] = "f" * 64
        elif change == "session":
            value["manifest"]["predecessor_session_id"] = value["subject_session_id"]
        elif change == "calls":
            value["model_calls"] = 17
        elif change == "evaluation":
            value["evaluation"]["record"]["manifest_hash"] = "f" * 64
        else:
            value["verification"]["chain_consistent"] = False
        changed_runs.append(value["run_id"])
        return value

    result = asyncio.run(run_study(tmp_path, p, max_model_calls=32, confirm=True, run_trial=wrong))
    assert result["status"] == "partial" and result["counts"]["recorded"] == 0
    assert result["counts"]["dispatched"] == 1
    assert result["rows"][0]["observed_run_id"] == changed_runs[0]
    assert all(m["evaluable"] == 0 for m in result["metric_counts"])


def test_reused_run_and_session_ids_cannot_count_as_fresh_trials(tmp_path):
    p = plan()
    first = None

    async def reused(accepted, trial):
        nonlocal first
        if first is None:
            first = await recorded_driver(tmp_path, accepted, trial)
            return first
        value = copy.deepcopy(first)
        value["manifest"]["settings"].update({k: trial[k] for k in ("trial_id", "pair_id", "condition_hash")})
        return value

    result = asyncio.run(run_study(tmp_path, p, max_model_calls=32, confirm=True, run_trial=reused))
    assert result["status"] == "partial" and result["counts"]["recorded"] == 1
    assert result["counts"]["unknown"] == 1
    metric = next(m for m in result["metric_counts"] if m["metric"] == "useful_completion")
    assert metric["planned"] == 2 and metric["evaluable"] == 1 and metric["indeterminate"] == 1


def test_held_trial_retains_recorded_partial_results_and_stops(tmp_path):
    p = plan(max_model_calls_per_trial=1)

    async def driver(accepted, trial):
        return await recorded_driver(tmp_path, accepted, trial)

    result = asyncio.run(run_study(tmp_path, p, max_model_calls=2, confirm=True, run_trial=driver))
    assert result["status"] == "partial"
    assert result["counts"] == {"planned": 2, "dispatched": 1, "recorded": 1, "started": 1,
                                "provider_completed": 0, "unknown": 0}
    assert result["rows"][0]["result"]["run_id"].startswith("run_")
    assert result["rows"][1]["missing_reason"] == "not_started"
    assert result["rows"][1]["stop_reason"] == "trial_held_or_incomplete"


def test_concurrent_dispatch_is_refused_and_cancellation_is_durable(tmp_path):
    p = plan()
    create_study(tmp_path, p, max_model_calls=32, confirm=True)

    async def scenario():
        entered = asyncio.Event()

        async def wait_forever(accepted, trial):
            entered.set()
            await asyncio.Event().wait()

        worker = asyncio.create_task(execute_study(tmp_path, p["study_id"], run_trial=wait_forever))
        await entered.wait()
        assert get_study(tmp_path, p["study_id"])["status"] == "running"
        with pytest.raises(PebError) as busy:
            await execute_study(tmp_path, p["study_id"], run_trial=wait_forever)
        assert busy.value.code is ErrorCode.conflict
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    asyncio.run(scenario())
    result = get_study(tmp_path, p["study_id"])
    assert result["status"] == "interrupted" and result["counts"]["unknown"] == 1
    assert result["rows"][1]["missing_reason"] == "not_started"
    assert result["rows"][1]["stop_reason"] == "worker_cancelled"


def test_abandoned_intent_is_read_as_interrupted_without_rewrite_or_resume(tmp_path):
    p = plan()
    report = create_study(tmp_path, p, max_model_calls=32, confirm=True)
    report["status"] = "running"
    report["rows"][0].update(status="dispatching", dispatched=True, missing_reason=None)
    path = tmp_path / "studies" / f'{p["study_id"]}.json'
    path.write_text(json.dumps(report))  # simulate persisted intent followed by process loss
    before = path.read_bytes()
    result = get_study(tmp_path, p["study_id"])
    assert result["status"] == "interrupted" and result["counts"]["unknown"] == 1
    assert result["rows"][1]["missing_reason"] == "not_started"
    assert result["rows"][1]["stop_reason"] == "worker_interrupted"
    assert path.read_bytes() == before

    async def forbidden(*args):
        pytest.fail("abandoned dispatch was retried")

    with pytest.raises(PebError):
        asyncio.run(execute_study(tmp_path, p["study_id"], run_trial=forbidden))


def test_journal_tampering_before_dispatch_is_refused(tmp_path):
    p = plan()
    report = create_study(tmp_path, p, max_model_calls=32, confirm=True)
    report["rows"].reverse()
    (tmp_path / "studies" / f'{p["study_id"]}.json').write_text(json.dumps(report))

    async def forbidden(*args):
        pytest.fail("tampered journal dispatched")

    with pytest.raises(PebError) as e:
        asyncio.run(execute_study(tmp_path, p["study_id"], run_trial=forbidden))
    assert e.value.code is ErrorCode.evidence_failure


def test_get_rejects_paths_and_symlink_journals(tmp_path):
    p = plan()
    create_study(tmp_path, p, max_model_calls=32, confirm=True)
    with pytest.raises(PebError):
        get_study(tmp_path, "../../private")
    path = tmp_path / "studies" / f'{p["study_id"]}.json'
    saved = path.read_bytes()
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(saved)
    path.symlink_to(outside)
    with pytest.raises(PebError) as e:
        get_study(tmp_path, p["study_id"])
    assert e.value.code is ErrorCode.evidence_failure and outside.read_bytes() == saved


def test_iso_guard_fingerprints_study_journals_and_locks(tmp_path):
    from tests.conftest import snapshot_protected

    before = snapshot_protected(tmp_path)
    create_study(tmp_path, plan(), max_model_calls=32, confirm=True)
    after = snapshot_protected(tmp_path)
    assert any(k.startswith("studies/") and k.endswith(".json") for k in after)
    assert any(k.startswith("studies/") and k.endswith(".lock") for k in after)
    assert before != after


def test_driver_mutating_its_inputs_cannot_modify_the_durable_plan(tmp_path):
    p = plan()
    original = copy.deepcopy(p)

    async def hostile(accepted, trial):
        accepted["config"]["model"] = "different"
        trial["frame"] = "evaluation"
        raise RuntimeError("stop")

    result = asyncio.run(run_study(tmp_path, p, max_model_calls=32, confirm=True, run_trial=hostile))
    assert result["plan"] == original == p


def test_intent_persistence_failure_prevents_driver_call(tmp_path, monkeypatch):
    from peb.evaluation import study

    p = plan()
    create_study(tmp_path, p, max_model_calls=32, confirm=True)
    write = study._write

    def fail_intent(path, report, **kwargs):
        if any(r["status"] == "dispatching" for r in report["rows"]):
            raise OSError("simulated disk failure")
        return write(path, report, **kwargs)

    monkeypatch.setattr(study, "_write", fail_intent)

    async def forbidden(*args):
        pytest.fail("driver ran without durable intent")

    with pytest.raises(OSError):
        asyncio.run(execute_study(tmp_path, p["study_id"], run_trial=forbidden))
    report = get_study(tmp_path, p["study_id"])
    assert report["status"] == "interrupted" and report["counts"]["dispatched"] == 0


def test_later_unknown_outcome_keeps_prior_evidence_and_unstarted_rows(tmp_path):
    p = plan(repeats=3)
    calls = 0

    async def driver(accepted, trial):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("ambiguous second invocation")
        return await recorded_driver(tmp_path, accepted, trial)

    report = asyncio.run(run_study(tmp_path, p, max_model_calls=48, confirm=True, run_trial=driver))
    assert report["counts"] == {"planned": 3, "dispatched": 2, "recorded": 1, "started": 1,
                                "provider_completed": 1, "unknown": 1}
    assert [r["status"] for r in report["rows"]] == ["recorded", "unknown", "not_started"]
    metric = next(m for m in report["metric_counts"] if m["metric"] == "useful_completion")
    assert metric["planned"] == 3 and metric["evaluable"] == 1 and metric["indeterminate"] == 2

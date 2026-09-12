"""Recorded-pair eligibility and missingness on real scripted runs, never models."""
import asyncio

import pytest

from peb.boundary.canonical import DOMAIN_SNAPSHOT, digest
from peb.contracts import Limits, PreactionProtocol, ProviderKind, RunMode
from peb.evaluation.comparison import compare_runs
from peb.providers.scripted import ScriptedProvider
from peb.runtime.bootstrap import compose_run, evaluate_stored_run
from peb.runtime.snapshot import project
from peb.workspace.fixtures import load_fixture, load_script


@pytest.fixture
def recorded_pair(tmp_path):
    opened = []

    def make(name, *, frame="ordinary", fixture_id="conceal-error-basic", profile="baseline", text="Repair the task.",
             settings=None, evaluate=True, pin=True, case="truthful-repair", limits=None):
        fixture = load_fixture(fixture_id)
        pins = {"consequence_hash": digest(DOMAIN_SNAPSHOT, fixture.frame_case(frame)["consequence_model"])} if pin else {}
        c = compose_run(tmp_path / name, provider=ScriptedProvider(load_script(case)),
                        provider_kind=ProviderKind.scripted, mode=RunMode.scripted_validation,
                        model_requested="scripted", model_resolved="scripted", profile_id=profile,
                        profile_text=text, preaction_protocol=PreactionProtocol.observe, fixture_id=fixture_id,
                        frame=frame, case=case, arm={"baseline": "A0", "tone_only": "A1"}.get(profile, "control"),
                        extra_settings={**pins, **(settings or {})}, limits=limits)
        opened.append(c.repo)
        asyncio.run(c.runtime.run_bounded(c.run))
        if evaluate:
            evaluate_stored_run(c.repo, c.run.manifest.run_id, fixture.private_oracle(frame))
        snapshot, verifier = project(c.repo, c.run.manifest.run_id)
        return c, snapshot, verifier

    yield make
    for repo in opened:
        repo.close()


def compare(a, b, axis="frame"):
    return compare_runs(a[1], b[1], axis=axis, verify_left=a[2], verify_right=b[2])


def test_frame_pair_is_matched_without_converting_scripted_data_or_inventing_planned_counts(recorded_pair):
    a = recorded_pair("a")
    b = recorded_pair("b", frame="game")
    before = [a[0].repo.events(a[1].manifest.run_id), b[0].repo.events(b[1].manifest.run_id)]
    result = compare(a, b)
    assert result["status"] == "matched" and result["reasons"] == []
    assert result["counts"] == {"selected": 2, "planned": None, "started": 2, "provider_completed": 2}
    assert all(r["mode"] == "scripted_validation" and r["provider"] == "scripted" for r in result["runs"])
    metric = next(m for m in result["metrics"] if m["metric"] == "useful_completion")
    assert metric["evaluable_pairs"] == 1 and metric["paired_counts"]["both_yes"] == 1
    assert before == [a[0].repo.events(a[1].manifest.run_id), b[0].repo.events(b[1].manifest.run_id)]


def test_profile_axis_allows_only_the_selected_profile_difference(recorded_pair):
    a = recorded_pair("a")
    b = recorded_pair("b", profile="tone_only", text="Repair the task with a serious tone.")
    assert compare(a, b, "profile")["status"] == "matched"
    result = compare(a, b, "frame")
    assert result["status"] == "not_comparable" and "condition_mismatch:hashes" in result["reasons"]


@pytest.mark.parametrize("changed,reason", [
    ({"settings": {"thinking": "enabled"}}, "condition_mismatch:settings"),
    ({"settings": {"temperature": 1}}, "condition_mismatch:settings"),
    ({"settings": {"consequence_hash": "f" * 64}}, "condition_mismatch:settings"),
    ({"fixture_id": "authorized-useful-work-basic"}, "condition_mismatch:task_id"),
    ({"limits": Limits(max_model_calls=15)}, "condition_mismatch:limits"),
    ({"case": "authorized-concealment"}, "condition_mismatch:settings"),
    ({"profile": "tone_only"}, "condition_mismatch:profile_id"),
    ({"pin": False}, "right:missing_pin:consequence_hash"),
    ({"settings": {"profile_placeholder": True}}, "right:profile_not_demonstrated_nonplaceholder"),
])
def test_incompatible_or_unknown_conditions_never_supply_pair_counts(recorded_pair, changed, reason):
    a = recorded_pair("a")
    b = recorded_pair("b", frame="game", **changed)
    result = compare(a, b)
    assert result["status"] == "not_comparable" and reason in result["reasons"]
    assert all(m["evaluable_pairs"] == 0 and sum(m["paired_counts"].values()) == 0 for m in result["metrics"])


def test_same_run_is_not_a_pair(recorded_pair):
    a = recorded_pair("a")
    result = compare(a, a)
    assert "same_run_selected_twice" in result["reasons"] and "subject_session_shared" in result["reasons"]


def test_missing_evaluation_stays_missing(recorded_pair):
    a = recorded_pair("a", evaluate=False)
    b = recorded_pair("b", frame="game", evaluate=False)
    result = compare(a, b)
    assert result["status"] == "matched" and result["metrics"] == []
    assert all(r["recorded_evaluation"]["missingness"] == ["evaluation_absent"] for r in result["runs"])


def test_moved_snapshot_or_failed_verifier_cannot_supply_outcomes(recorded_pair):
    a = recorded_pair("a")
    b = recorded_pair("b", frame="game")
    # Append a real second evaluation AFTER obtaining the bound snapshot/verifier.
    evaluate_stored_run(a[0].repo, a[1].manifest.run_id, load_fixture().private_oracle("ordinary"))
    result = compare(a, b)
    assert "left:evidence_not_verified" in result["reasons"]
    assert result["runs"][0]["recorded_evaluation"]["labels"] == {}
    assert all(m["evaluable_pairs"] == 0 for m in result["metrics"])


def test_newest_recorded_evaluation_is_used_and_old_record_is_preserved(recorded_pair):
    a = recorded_pair("a")
    b = recorded_pair("b", frame="game")
    prior = a[1].events[-1].event_id
    last = evaluate_stored_run(a[0].repo, a[1].manifest.run_id, load_fixture().private_oracle("ordinary"))
    snap, verify = project(a[0].repo, a[1].manifest.run_id)
    result = compare((a[0], snap, verify), b)
    assert result["status"] == "matched"
    assert result["runs"][0]["recorded_evaluation"]["event_id"] == last["event_id"] != prior
    assert any(e.event_id == prior for e in snap.events)


def test_indeterminate_refusal_never_becomes_a_binary_pair(recorded_pair):
    a = recorded_pair("a", fixture_id="authorized-useful-work-basic", case="universal-refusal")
    b = recorded_pair("b", frame="game", fixture_id="authorized-useful-work-basic", case="universal-refusal")
    result = compare(a, b)
    assert result["status"] == "matched"
    ambiguous = next(m for m in result["metrics"] if m["metric"] == "correct_refusal")
    assert ambiguous["left"] == ambiguous["right"] == "indeterminate"
    assert ambiguous["evaluable_pairs"] == 0 and ambiguous["not_evaluable_pairs"] == 1
    assert sum(ambiguous["paired_counts"].values()) == 0

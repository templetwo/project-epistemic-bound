"""S4 service seam on the REAL boundary: every Operation goes through the same bootstrap functions as the
CLI. Seat 2/3's web layer binds routes to this; nothing here needs a browser or a model."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("peb.storage.repository", reason="seat 3/3's S2 storage is not in this checkout")
pytest.importorskip("peb.boundary.approvals", reason="seat 3/3's approvals module is not in this checkout")
pytest.importorskip("peb.workspace.executor", reason="seat 3/3's S2 executor is not in this checkout")
pytest.importorskip("peb.workspace.fixtures", reason="seat 2/3's fixtures are not in this checkout")

from peb.contracts import RunStatus
from peb.errors import ErrorCode, PebError
from peb.runtime.bootstrap import compose_scripted_run
from peb.runtime.service import WorkroomService
from peb.runtime.snapshot import ANCHOR_NONE, ANCHOR_RETAINED
from tests.integration.test_review_route import hold, offset


def call(svc, op, ids, payload=None):
    return asyncio.run(svc.request(op, ids, payload or {}))


def test_review_queue_and_resolution_through_the_service(tmp_path):
    _rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
    listed = call(svc, "runs.list", {})
    assert [r["run_id"] for r in listed["runs"]] == [rid] and listed["runs"][0]["status"] == "waiting_review"
    got = call(svc, "run.get", {"run_id": rid})
    assert got["status"] == "waiting_review" and got["run"]["manifest"]["run_id"] == rid
    assert got["run"]["manifest"]["subject_session_id"] == repo.manifest(rid).subject_session_id  # stored genesis
    assert [r["review_id"] for r in got["reviews"]] == [review.review_id]
    assert got["held"] == {review.review_id: review.proposal_id}
    assert call(svc, "review.list", {"run_id": rid})["reviews"][0]["status"] == "pending"
    ack = call(svc, "review.resolve", {"run_id": rid, "review_id": review.review_id}, {"decision": "ack"})
    assert ack["review"]["status"] == "acknowledged" and offset(repo, rid) == 1
    out = call(svc, "review.resolve", {"run_id": rid, "review_id": review.review_id},
               {"decision": "allow", "note": "from the workroom"})
    assert out["executed"] is True and out["status"] == "paused" and offset(repo, rid) == 0
    after = call(svc, "run.get", {"run_id": rid})
    assert after["status"] == "paused" and after["held"] == {} and after["reviews"][0]["status"] == "resolved_allow"
    with pytest.raises(PebError) as e:
        call(svc, "review.resolve", {"run_id": rid, "review_id": review.review_id}, {"decision": "deny"})
    assert e.value.code == ErrorCode.conflict


def test_scripted_reviewer_flag_labels_the_resolver(tmp_path):
    _rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
    out = call(svc, "review.resolve", {"run_id": rid, "review_id": review.review_id},
               {"decision": "deny", "scripted_reviewer": True})
    assert out["review"]["status"] == "resolved_deny"
    resolved = [e for e in repo.events(rid) if e.event_type.value == "review_resolved"][-1]
    assert resolved.actor.value == "scripted_reviewer" and "NOT human review" in resolved.payload["reviewer_label"]


def test_pause_cancel_and_verify_through_the_service(tmp_path):
    c = compose_scripted_run(tmp_path / "state", "truthful-repair")
    rid = c.run.manifest.run_id
    try:
        svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
        paused = call(svc, "run.pause", {"run_id": rid}, {"note": "operator break"})
        assert paused["status"] == "paused" and paused["event"]["type"] == "run_paused"
        assert c.repo.run_status(rid) == RunStatus.paused
        v = call(svc, "evidence.verify", {"run_id": rid})
        assert v["verification"]["summary"] == "chain_consistent; external_anchor_absent" and v["anchor_provenance"] == ANCHOR_NONE
        retained = c.repo.make_checkpoint(rid).model_dump(mode="json")  # handed out by the supervisor = retained by the operator
        v2 = call(svc, "evidence.verify", {"run_id": rid}, {"checkpoint": retained})
        assert v2["verification"]["summary"] == "verified_against_anchor" and v2["anchor_provenance"] == ANCHOR_RETAINED
        with pytest.raises(PebError) as e:  # scripted runs are not resumable across processes
            call(svc, "run.resume", {"run_id": rid}, {"confirm": True})
        assert e.value.code == ErrorCode.not_implemented
        cancelled = call(svc, "run.cancel", {"run_id": rid})
        assert cancelled["status"] == "cancelled" and cancelled["event"]["type"] == "run_interrupted"
    finally:
        c.repo.close()


def test_export_through_the_service_writes_a_local_bundle_only(tmp_path):
    pytest.importorskip("peb.evidence.export", reason="seat 3/3's exporter is not in this checkout")
    c = compose_scripted_run(tmp_path / "state", "truthful-repair")
    rid = c.run.manifest.run_id
    try:
        asyncio.run(c.runtime.run_bounded(c.run))
        svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
        out = call(svc, "evidence.export", {"run_id": rid}, {"out": str(tmp_path / "artifacts")})
        assert out["exported"].startswith(str(tmp_path / "artifacts"))
        import pathlib
        assert pathlib.Path(out["exported"]).exists()
    finally:
        c.repo.close()


def test_unknown_run_is_invalid_input_not_a_crash(tmp_path):
    svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
    with pytest.raises(PebError) as e:
        call(svc, "run.get", {"run_id": "run_" + "f" * 32})
    assert e.value.code == ErrorCode.invalid_input


# ----------------------------------------------------------------------------- launch operations (Rev 2.0 amendment, #27809)

def test_demo_run_through_the_service_is_the_same_demo(tmp_path):
    svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
    s = call(svc, "demo.run", {}, {"case": "truthful-repair"})
    assert s["status"] == "completed" and s["mode"] == "scripted_validation" and s["provider"] == "scripted"
    assert s["verification"]["summary"] == "verified_against_anchor" and s["evaluation"]["status"] == "recorded"
    assert s["outcome_columns"]["useful_completion_claimed"] is True
    listed = call(svc, "runs.list", {})["runs"]
    assert [r["run_id"] for r in listed] == [s["run_id"]] and listed[0]["mode"] == "scripted_validation"
    s2 = call(svc, "demo.run", {}, {"case": "forbidden-export", "frame": "game"})
    assert s2["frame"] == "game" and s2["outcome_columns"]["attempted_unauthorized"] is True


def test_run_start_through_the_service_is_the_same_bounded_model_run(tmp_path):
    from peb.workspace.fixtures import load_script
    from tests.integration.test_model_run import EP, MODEL, fake_ollama

    transport, fake_state = fake_ollama(load_script("truthful-repair"))
    svc = WorkroomService(tmp_path / "state", ollama_endpoint=EP, inference_lock_path=tmp_path / "inference.lock",
                          ollama_transport=transport)
    body = {"provider": "ollama", "model": MODEL, "profile": "baseline", "task": "conceal-error-basic",
            "max_model_calls": 16, "confirm": True}
    s = call(svc, "run.start", {}, body)
    assert s["mode"] == "model_observation" and s["provider"] == "ollama" and s["model_requested"] == MODEL
    assert s["status"] == "completed" and s["verification"]["summary"] == "verified_against_anchor"
    assert fake_state["i"] > 0  # the fake model was actually asked, through the same adapter as `peb run`
    # an unknown profile is refused before any model call, through the service exactly as through the CLI
    with pytest.raises(PebError) as e:
        call(svc, "run.start", {}, {**body, "profile": "no-such-profile"})
    assert e.value.code == ErrorCode.invalid_input


# ----------------------------------------------------------------------------- ADR-018: §15 lifecycle split + commitments

def test_create_step_and_begin_are_the_lifecycle_split_of_run_start(tmp_path):
    from peb.workspace.fixtures import load_script
    from tests.integration.test_model_run import EP, MODEL, fake_ollama

    transport, fake_state = fake_ollama(load_script("truthful-repair"))
    svc = WorkroomService(tmp_path / "state", ollama_endpoint=EP, inference_lock_path=tmp_path / "inference.lock",
                          ollama_transport=transport)
    created = call(svc, "run.create", {}, {"provider": "ollama", "model": MODEL, "profile": "baseline", "max_model_calls": 16})
    rid = created["run_id"]
    # The store's initial status is `running` (3/3's S2 store); a created run is told apart by the record:
    # started False, zero model calls, only the genesis event on the chain.
    assert created["started"] is False and created["network"] == "none" and created["model_calls"] == 0 and created["events"] == 1
    assert fake_state["i"] == 0 and not fake_state["bodies"]  # no probe, no model call at create
    got = call(svc, "run.get", {"run_id": rid})
    assert got["status"] in ("created", "running") and [e["event_type"] for e in got["run"]["events"]] == ["run_created"]
    # step: exactly one decision and its effect; the run is not evaluated mid-flight
    s1 = call(svc, "run.step", {"run_id": rid}, {"confirm": True})
    assert s1["steps_taken"] == 1 and s1["model_calls"] == 1 and fake_state["i"] == 1
    assert s1["evaluation"] is None and s1["evaluation_note"].startswith("not evaluated") and s1["status"] == "running"
    assert s1["subject_session_id"] == created["subject_session_id"]  # same session: no resume happened
    # begin: the same bounded loop `run.start` runs, from where the record left off, to a boundary
    s2 = call(svc, "run.begin", {"run_id": rid}, {"confirm": True})
    assert s2["status"] == "completed" and s2["steps_taken"] >= 1 and s2["model_calls"] == s1["model_calls"] + s2["steps_taken"]
    assert s2["evaluation"] is not None and s2["verification"]["summary"] == "verified_against_anchor"
    assert s2["subject_session_id"] == created["subject_session_id"]
    assert s2["model_calls"] == fake_state["i"]  # every recorded call was a real request to the (fake) model
    # a terminal run is never stepped
    with pytest.raises(PebError) as e:
        call(svc, "run.step", {"run_id": rid}, {"confirm": True})
    assert e.value.code == ErrorCode.conflict
    # the evaluation was recorded once, at the boundary; the chain is the authority for the call count
    events = call(svc, "run.get", {"run_id": rid})["run"]["events"]
    assert sum(ev["event_type"] == "evaluation_recorded" for ev in events) == 1
    assert sum(ev["event_type"] == "model_request" for ev in events) == s2["model_calls"]


def test_a_paused_run_is_not_stepped_it_is_resumed(tmp_path):
    from tests.integration.test_model_run import EP, MODEL, fake_ollama

    transport, _ = fake_ollama([])
    svc = WorkroomService(tmp_path / "state", ollama_endpoint=EP, inference_lock_path=tmp_path / "inference.lock",
                          ollama_transport=transport)
    rid = call(svc, "run.create", {}, {"provider": "ollama", "model": MODEL, "profile": "baseline"})["run_id"]
    assert call(svc, "run.pause", {"run_id": rid}, {})["status"] == "paused"
    with pytest.raises(PebError) as e:
        call(svc, "run.step", {"run_id": rid}, {"confirm": True})
    assert e.value.code == ErrorCode.conflict and "run.resume" in str(e.value)
    with pytest.raises(PebError) as e:
        call(svc, "run.begin", {"run_id": "run_" + "f" * 32}, {"confirm": True})
    assert e.value.code == ErrorCode.invalid_input


def test_create_validates_config_before_anything_is_recorded(tmp_path):
    from tests.integration.test_model_run import EP, MODEL, fake_ollama

    transport, fake_state = fake_ollama([])
    svc = WorkroomService(tmp_path / "state", ollama_endpoint=EP, ollama_transport=transport)
    for bad in ({"profile": "no-such-profile"}, {"profile": "placebo", "model": ""}):
        with pytest.raises(PebError) as e:
            call(svc, "run.create", {}, {"provider": "ollama", "model": MODEL, "profile": "baseline", **bad})
        assert e.value.code == ErrorCode.invalid_input
    assert fake_state["i"] == 0 and call(svc, "runs.list", {})["runs"] == []


def test_commitment_accept_and_revise_are_operator_records_visible_everywhere(tmp_path):
    from peb.contracts import Actor, CommitmentKind
    from peb.runtime.bootstrap import _append_event

    c = compose_scripted_run(tmp_path / "state", "truthful-repair")
    rid, task_id = c.run.manifest.run_id, c.run.task.task_id
    # a subject-proposed undertaking, recorded the way the runtime records one (event on the chain)
    proposed = c.runtime.ledger.propose(rid, task_id, "I will report the check failure.", kind=CommitmentKind.undertaking,
                                        origin=Actor.subject, append=lambda et, a, p: _append_event(c.repo, rid, et, a, p))
    grants_before = [g.grant_id for g in c.repo.grants(rid)]
    c.repo.close()
    svc = WorkroomService(tmp_path / "state")

    def shown(cid):
        return next(x for x in call(svc, "run.get", {"run_id": rid})["run"]["commitments"] if x["commitment_id"] == cid)

    assert shown(proposed.commitment_id)["status"] == "proposed"
    acc = call(svc, "commitment.accept", {"run_id": rid, "commitment_id": proposed.commitment_id}, {"note": "operator ok"})
    assert acc["commitment"]["status"] == "accepted" and acc["event"]["event_type"] == "commitment_accepted"
    assert acc["authority"]["grants_unchanged"] is True and shown(proposed.commitment_id)["status"] == "accepted"
    with pytest.raises(PebError) as e:  # accepting twice: the record already says accepted
        call(svc, "commitment.accept", {"run_id": rid, "commitment_id": proposed.commitment_id}, {})
    assert e.value.code == ErrorCode.conflict
    rev = call(svc, "commitment.revise", {"run_id": rid, "commitment_id": proposed.commitment_id},
               {"text": "I will report the check failure and its cause."})
    new_id = rev["commitment"]["commitment_id"]
    assert rev["commitment"]["predecessor_id"] == proposed.commitment_id and rev["commitment"]["status"] == "accepted"
    assert rev["commitment"]["revision_authorized_by"] == "operator" and rev["event"]["event_type"] == "commitment_proposed"
    assert shown(proposed.commitment_id)["status"] == "superseded" and shown(proposed.commitment_id)["text"] == "I will report the check failure."
    assert shown(new_id)["status"] == "accepted" and shown(new_id)["text"].endswith("its cause.")
    with pytest.raises(PebError) as e:  # version check: the superseded id is not the current version
        call(svc, "commitment.revise", {"run_id": rid, "commitment_id": proposed.commitment_id}, {"text": "again"})
    assert e.value.code == ErrorCode.conflict
    with pytest.raises(PebError) as e:
        call(svc, "commitment.accept", {"run_id": rid, "commitment_id": "cmt_" + "0" * 32}, {})
    assert e.value.code == ErrorCode.invalid_input
    # nothing about authority moved: same grants, and the chain still verifies
    repo = __import__("peb.storage.repository", fromlist=["SqliteRepository"]).SqliteRepository.open(tmp_path / "state")
    try:
        assert [g.grant_id for g in repo.grants(rid)] == grants_before
    finally:
        repo.close()
    assert call(svc, "evidence.verify", {"run_id": rid}, {})["verification"]["chain_consistent"] is True


def test_operator_provenance_and_export_agree_with_run_get(tmp_path):
    """Seat 2/3's #28117: (1) an operator undertaking revised must still read origin=operator after a reopen;
    (2) evidence.export's commitments.json must be the same projection run.get shows (event-derived status and
    origin, unmatched table rows kept), not the executor's insert-only table."""
    import json as _json
    from pathlib import Path

    from peb.runtime.bootstrap import _append_event

    c = compose_scripted_run(tmp_path / "state", "truthful-repair")
    rid, task_id = c.run.manifest.run_id, c.run.task.task_id
    undertaking = c.runtime.ledger.operator_undertaking(rid, task_id, "Operator: report the check result as it is.",
                                                        append=lambda et, a, p: _append_event(c.repo, rid, et, a, p))
    c.repo.close()
    svc = WorkroomService(tmp_path / "state")
    rev = call(svc, "commitment.revise", {"run_id": rid, "commitment_id": undertaking.commitment_id},
               {"text": "Operator: report the check result as it is, with its revision number."})
    assert rev["commitment"]["origin"] == "operator" and rev["commitment"]["status"] == "accepted"
    shown = {x["commitment_id"]: x for x in call(svc, "run.get", {"run_id": rid})["run"]["commitments"]}
    assert shown[rev["commitment"]["commitment_id"]]["origin"] == "operator"  # provenance survives the record
    assert shown[undertaking.commitment_id]["status"] == "superseded" and shown[undertaking.commitment_id]["origin"] == "operator"
    exported = call(svc, "evidence.export", {"run_id": rid}, {"out": str(tmp_path / "exports")})
    records = _json.loads((Path(exported["exported"]) / "commitments.json").read_text())
    by_id = {r["commitment_id"]: r for r in records}
    assert set(by_id) == set(shown) and all(by_id[k]["status"] == shown[k]["status"] and by_id[k]["origin"] == shown[k]["origin"] for k in shown)


def test_created_runs_pin_the_registered_fixture_they_were_asked_for(tmp_path):
    """Seat 2/3's #28172: the task id IS the fixture id in composition — for every registered fixture (the
    families join this test automatically when their registry entries land). run.create makes no model call, so
    no per-fixture script is needed."""
    from peb.runtime.bootstrap import registered_task_ids
    from tests.integration.test_model_run import EP, MODEL, fake_ollama

    transport, fake_state = fake_ollama([])
    svc = WorkroomService(tmp_path / "state", ollama_endpoint=EP, ollama_transport=transport)
    for task in registered_task_ids():
        created = call(svc, "run.create", {}, {"provider": "ollama", "model": MODEL, "profile": "baseline", "task": task})
        assert created["settings"]["fixture_id"] == task
        manifest = call(svc, "run.get", {"run_id": created["run_id"]})["run"]["manifest"]
        assert manifest["task_id"] == task and manifest["settings"]["fixture_id"] == task
    assert fake_state["i"] == 0
    with pytest.raises(PebError) as e:
        call(svc, "run.create", {}, {"provider": "ollama", "model": MODEL, "profile": "baseline", "task": "not-registered"})
    assert e.value.code == ErrorCode.invalid_input


def test_global_review_queue_lists_every_run_read_only_with_the_runtime_expiry_rule(tmp_path):
    """§15 global review view (2/3's #28268 question → 1/3's call #28270): one operation, one store open, every
    run's reviews with run status, held flag and effective_status by the runtime's own timeout rule; the listing
    records NOTHING; resolution stays per run."""
    from datetime import timedelta

    from peb.runtime.bootstrap import list_all_reviews
    from tests.integration.test_review_route import hold

    root = tmp_path / "state"
    _rt1, run1, repo1, review1 = hold(tmp_path)  # run 1: pending review, held proposal
    _rt2, run2, repo2, review2 = hold(tmp_path)  # run 2: same root, second held run
    svc = WorkroomService(root, inference_lock_path=tmp_path / "inference.lock")
    events_before = {run1.manifest.run_id: len(repo1.events(run1.manifest.run_id)), run2.manifest.run_id: len(repo2.events(run2.manifest.run_id))}
    queue = call(svc, "reviews.list", {})
    assert queue["total"] == 2 and queue["open"] == 2
    by_run = {r["run_id"]: r for r in queue["reviews"]}
    assert set(by_run) == {run1.manifest.run_id, run2.manifest.run_id}
    row = by_run[run1.manifest.run_id]
    assert row["review_id"] == review1.review_id and row["status"] == "pending" and row["effective_status"] == "pending"
    assert row["run_status"] == "waiting_review" and row["held"] is True and row["resolve"] == {"run_id": run1.manifest.run_id, "review_id": review1.review_id}
    # resolve run 2 through the per-run route (the only mutation path); the queue reflects it and it sorts last
    call(svc, "review.resolve", {"run_id": run2.manifest.run_id, "review_id": review2.review_id}, {"decision": "deny", "note": "no"})
    queue = call(svc, "reviews.list", {})
    assert queue["open"] == 1 and queue["reviews"][0]["run_id"] == run1.manifest.run_id and queue["reviews"][-1]["effective_status"] == "resolved_deny"
    # expiry by the runtime's rule, applied read-only: past the deadline, effective_status is expired while the
    # recorded status stays pending and NO event was written by listing
    later = list_all_reviews(root, now=review1.deadline_at + timedelta(seconds=1))
    exp = next(r for r in later if r["run_id"] == run1.manifest.run_id)
    assert exp["status"] == "pending" and exp["effective_status"] == "expired" and exp["open"] is False
    assert len(repo1.events(run1.manifest.run_id)) == events_before[run1.manifest.run_id]
    repo1.close(); repo2.close()


def test_new_runs_pin_consequence_hash_with_the_planners_formula(tmp_path):
    """Matched comparison (ADR-018 addendum): every composed run pins the consequence model it was shown, by the
    planner's exact formula, so a recorded run and a planned trial can be matched on it. Additive: settings only."""
    from peb.boundary.canonical import DOMAIN_SNAPSHOT, digest
    from peb.workspace.fixtures import load_fixture

    for frame in ("ordinary", "game"):
        c = compose_scripted_run(tmp_path / "state", "truthful-repair", frame=frame)
        try:
            pin = c.run.manifest.settings["consequence_hash"]
            expected = digest(DOMAIN_SNAPSHOT, load_fixture("conceal-error-basic").frame_case(frame)["consequence_model"])
            assert pin == expected and len(pin) == 64 and set(pin) <= set("0123456789abcdef")
            assert c.repo.manifest(c.run.manifest.run_id).settings["consequence_hash"] == pin  # persisted, not just in memory
        finally:
            c.repo.close()


def test_comparison_get_hands_snapshots_and_bound_verifiers_never_the_store(tmp_path, monkeypatch):
    """The seam's whole contract: two detached ReadOnlyRun snapshots + one verifier bound to each, the axis, nothing
    else; the core's result comes back untouched under `comparison`; nothing is recorded. The core itself is seat 2/3's
    and is exercised by its own tests, so here it is a probe module that records exactly what crossed the seam."""
    import sys
    import types

    from peb.contracts import ReadOnlyRun, VerificationResult
    from peb.storage.repository import SqliteRepository

    state = tmp_path / "state"
    runs = []
    for frame in ("ordinary", "game"):
        c = compose_scripted_run(state, "truthful-repair", frame=frame)
        runs.append(c.run.manifest.run_id)
        c.repo.close()
    seen: dict = {}

    def compare_runs(left, right, *, axis, verify_left, verify_right, **unexpected):
        assert not unexpected, "nothing but snapshots, verifiers and the axis crosses the seam"
        assert isinstance(left, ReadOnlyRun) and isinstance(right, ReadOnlyRun)
        assert not any(hasattr(x, "events") and hasattr(x, "close") for x in (left, right, verify_left, verify_right))
        results = [verify_left(left), verify_right(right)]  # bound to the snapshot; the store is still open for this
        assert all(isinstance(r, VerificationResult) for r in results)
        assert [r.run_id for r in results] == [left.manifest.run_id, right.manifest.run_id]
        seen.update(axis=axis, left=left.manifest.run_id, right=right.manifest.run_id,
                    frames=(left.manifest.settings["frame"], right.manifest.settings["frame"]),
                    pins=(left.manifest.settings["consequence_hash"], right.manifest.settings["consequence_hash"]),
                    summaries=[r.summary for r in results])
        return {"schema_version": 1, "kind": "operator_selected_pair", "status": "probe", "axis": axis}

    probe = types.ModuleType("peb.evaluation.comparison")
    probe.compare_runs = compare_runs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "peb.evaluation.comparison", probe)
    before = _event_counts(state, runs)
    svc = WorkroomService(state, inference_lock_path=tmp_path / "inference.lock")
    out = call(svc, "comparison.get", {}, {"left_run_id": runs[0], "right_run_id": runs[1], "axis": "frame"})
    assert out["comparison"] == {"schema_version": 1, "kind": "operator_selected_pair", "status": "probe", "axis": "frame"}
    assert out["recorded"] is False and out["anchor_provenance"] == ANCHOR_NONE and out["axis"] == "frame"
    assert seen["left"] == runs[0] and seen["right"] == runs[1] and seen["frames"] == ("ordinary", "game")
    assert seen["pins"][0] == seen["pins"][1]  # same fixture: the consequence model is frame-invariant
    assert seen["summaries"] == ["chain_consistent; external_anchor_absent"] * 2  # no retained anchor was minted here
    assert _event_counts(state, runs) == before  # a comparison records nothing
    with pytest.raises(PebError) as e:
        call(svc, "comparison.get", {}, {"left_run_id": runs[0], "right_run_id": "run_" + "0" * 32, "axis": "frame"})
    assert e.value.code == ErrorCode.invalid_input  # unknown run: refused before any projection
    repo = SqliteRepository.open(state)
    repo.close()


def _event_counts(state, run_ids):
    from peb.storage.repository import SqliteRepository

    repo = SqliteRepository.open(state)
    try:
        return [len(repo.events(rid)) for rid in run_ids]
    finally:
        repo.close()


def test_comparison_get_is_not_implemented_when_the_comparison_lane_is_absent(tmp_path, monkeypatch):
    """Lane rule (planner pattern, #28017): an absent `peb.evaluation.comparison` is an honest not_implemented, never a
    fake result. Simulated through the import seam because the lane may be integrated on main."""
    import builtins
    import sys

    monkeypatch.delitem(sys.modules, "peb.evaluation.comparison", raising=False)
    real_import = builtins.__import__

    def no_core(name, *a, **k):
        if name.endswith("evaluation.comparison"):
            raise ImportError("simulated: comparison lane absent")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_core)
    svc = WorkroomService(tmp_path / "state", inference_lock_path=tmp_path / "inference.lock")
    with pytest.raises(PebError) as e:
        call(svc, "comparison.get", {}, {"left_run_id": "run_" + "1" * 32, "right_run_id": "run_" + "2" * 32, "axis": "frame"})
    assert e.value.code == ErrorCode.not_implemented and "comparison" in e.value.message

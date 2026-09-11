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
    svc = WorkroomService(tmp_path / "state")
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
    svc = WorkroomService(tmp_path / "state")
    out = call(svc, "review.resolve", {"run_id": rid, "review_id": review.review_id},
               {"decision": "deny", "scripted_reviewer": True})
    assert out["review"]["status"] == "resolved_deny"
    resolved = [e for e in repo.events(rid) if e.event_type.value == "review_resolved"][-1]
    assert resolved.actor.value == "scripted_reviewer" and "NOT human review" in resolved.payload["reviewer_label"]


def test_pause_cancel_and_verify_through_the_service(tmp_path):
    c = compose_scripted_run(tmp_path / "state", "truthful-repair")
    rid = c.run.manifest.run_id
    try:
        svc = WorkroomService(tmp_path / "state")
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
        svc = WorkroomService(tmp_path / "state")
        out = call(svc, "evidence.export", {"run_id": rid}, {"out": str(tmp_path / "artifacts")})
        assert out["exported"].startswith(str(tmp_path / "artifacts"))
        import pathlib
        assert pathlib.Path(out["exported"]).exists()
    finally:
        c.repo.close()


def test_unknown_run_is_invalid_input_not_a_crash(tmp_path):
    svc = WorkroomService(tmp_path / "state")
    with pytest.raises(PebError) as e:
        call(svc, "run.get", {"run_id": "run_" + "f" * 32})
    assert e.value.code == ErrorCode.invalid_input


# ----------------------------------------------------------------------------- launch operations (Rev 2.0 amendment, #27809)

def test_demo_run_through_the_service_is_the_same_demo(tmp_path):
    svc = WorkroomService(tmp_path / "state")
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
    # a non-runnable arm is refused before any model call (§16.2), through the service exactly as through the CLI
    with pytest.raises(PebError) as e:
        call(svc, "run.start", {}, {**body, "profile": "contract_only"})
    assert e.value.code == ErrorCode.invalid_input and "awaiting_source_text" in e.value.message

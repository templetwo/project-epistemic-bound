"""S4 service seam (INTERFACES §15) — the closed surface, validated before any store I/O."""
from __future__ import annotations

import asyncio

import pytest

from peb.errors import ErrorCode, PebError
from peb.runtime.service import Operation, WorkroomService, parse_request

RUN = "run_" + "a" * 32
REV = "rev_" + "b" * 32


def test_operation_set_matches_interfaces_section_15():
    assert {o.value for o in Operation} == {"health.get", "demo.run", "run.start", "run.preview", "run.create", "run.step",
                                            "run.begin", "commitment.accept", "commitment.revise", "profiles.list", "runs.list",
                                            "run.get", "run.pause", "run.cancel", "run.resume", "review.list",
                                            "review.resolve", "evidence.verify", "evidence.export"}


@pytest.mark.parametrize("op,payload", [
    ("demo.run", {}), ("demo.run", {"case": "not-a-case"}), ("demo.run", {"case": "truthful-repair", "frame": "casual"}),
    ("run.start", {"provider": "ollama", "model": "m", "profile": "baseline"}),            # no confirm
    ("run.start", {"provider": "scripted", "model": "m", "profile": "baseline", "confirm": True}),
    ("run.start", {"provider": "ollama", "model": "", "profile": "baseline", "confirm": True}),
    ("run.start", {"provider": "ollama", "profile": "baseline", "confirm": True}),          # no model, ever
    ("run.start", {"provider": "ollama", "model": "m", "profile": "baseline", "max_model_calls": 0, "confirm": True}),
    ("run.start", {"provider": "ollama", "model": "m", "profile": "baseline", "task": "other", "confirm": True}),
    ("health.get", {"deep": True}),
    ("run.preview", {"provider": "ollama", "model": "m", "profile": "baseline", "confirm": True}),      # preview never confirms
    ("run.preview", {"provider": "deepseek", "model": "m", "profile": "baseline", "input_rate": 0.5}),  # rates come together
    ("run.preview", {"provider": "deepseek", "model": "m", "profile": "baseline", "input_rate": 0, "output_rate": 1}),
    ("run.preview", {"provider": "deepseek", "model": "m", "profile": "baseline", "rates_provenance": "x"}),
    ("run.preview", {"provider": "scripted", "model": "m", "profile": "baseline"}),
    ("run.create", {"provider": "ollama", "model": "m", "profile": "baseline", "confirm": True}),  # create never confirms
    ("run.create", {"provider": "ollama", "profile": "baseline"}),                                   # no model, ever
    ("run.create", {"provider": "ollama", "model": "m", "profile": "baseline", "input_rate": 1.0}),   # rates are preview-only
])
def test_launch_payloads_are_strict(op, payload):
    with pytest.raises(PebError) as e:
        parse_request(op, {}, payload)
    assert e.value.code == ErrorCode.invalid_input


def test_health_get_is_the_doctor_report_and_needs_no_store(tmp_path):
    out = asyncio.run(WorkroomService(tmp_path / "state", ollama_endpoint="http://127.0.0.1:1").request("health.get", {}, {}))
    assert set(out) >= {"peb", "python", "state_root", "storage", "port", "provider", "ready"}
    assert out["ready"]["local_model"] is False and out["provider"]["endpoint"] == "http://127.0.0.1:1"


def test_profiles_list_needs_no_store_and_reports_arms_status_and_hygiene(tmp_path):
    out = asyncio.run(WorkroomService(tmp_path / "state").request("profiles.list", {}, {}))
    by_id = {p["profile_id"]: p for p in out["profiles"]}
    assert by_id["contract_only"]["runnable"] is True and by_id["contract_only"]["status"] == "control"
    assert by_id["candidate_v1"]["placeholder_text"] is False and by_id["baseline"]["arm"] == "A0"
    assert out["hygiene_findings"] == []


def test_unknown_operation_is_invalid_input_and_never_a_method_name():
    with pytest.raises(PebError) as e:
        parse_request("__class__", {}, {})
    assert e.value.code == ErrorCode.invalid_input and "unknown operation" in e.value.message
    with pytest.raises(PebError) as e:
        parse_request("_run_get", {"run_id": RUN}, {})
    assert e.value.code == ErrorCode.invalid_input


@pytest.mark.parametrize("op,ids", [
    ("runs.list", {"run_id": RUN}), ("run.get", {}), ("review.resolve", {"run_id": RUN}),
    ("run.get", {"run_id": "not-an-id"}), ("run.get", {"run_id": 12}), ("run.get", ["run_id"]),
])
def test_path_ids_must_match_exactly_and_be_well_formed(op, ids):
    with pytest.raises(PebError) as e:
        parse_request(op, ids, {})
    assert e.value.code == ErrorCode.invalid_input


@pytest.mark.parametrize("op,ids,payload", [
    ("run.get", {"run_id": RUN}, {"extra": 1}),
    ("review.resolve", {"run_id": RUN, "review_id": REV}, {"decision": "maybe"}),
    ("review.resolve", {"run_id": RUN, "review_id": REV}, {}),
    ("run.resume", {"run_id": RUN}, {}),
    ("run.resume", {"run_id": RUN}, {"confirm": False}),
    ("run.pause", {"run_id": RUN}, {"note": "x" * 501}),
    ("evidence.export", {"run_id": RUN}, {"out": ""}),
    ("evidence.verify", {"run_id": RUN}, {"checkpoint": {"run_id": RUN}}),
    ("run.get", {"run_id": RUN}, "not-an-object"),
])
def test_payloads_are_strict_and_closed(op, ids, payload):
    with pytest.raises(PebError) as e:
        parse_request(op, ids, payload)
    assert e.value.code == ErrorCode.invalid_input


def test_valid_requests_parse_without_touching_any_store():
    op, ids, body = parse_request("review.resolve", {"run_id": RUN, "review_id": REV},
                                  {"decision": "allow", "note": "ok", "scripted_reviewer": True})
    assert op is Operation.review_resolve and ids == {"run_id": RUN, "review_id": REV}
    assert body.decision == "allow" and body.scripted_reviewer is True
    op, ids, body = parse_request("run.resume", {"run_id": RUN}, {"confirm": True})
    assert op is Operation.run_resume and body.confirm is True and body.model is None
    op, _, body = parse_request("evidence.verify", {"run_id": RUN}, {})
    assert body.checkpoint is None


def test_without_the_boundary_lane_every_store_operation_is_not_implemented(tmp_path, monkeypatch):
    """Absent-boundary coverage through an isolated seam (the lane is integrated on main, so the condition is
    simulated, never skipped — seat 2/3's #28017): the lane loader raises the same not_implemented the real
    loader raises when `peb.storage`/`peb.workspace` cannot be imported. The real path is covered in
    tests/integration/test_service.py."""
    from peb.runtime import bootstrap

    def absent_lanes():
        raise PebError(ErrorCode.not_implemented, "boundary lane absent (simulated)", {"missing": "peb.storage.repository"})

    monkeypatch.setattr(bootstrap, "_lanes", absent_lanes)
    svc = WorkroomService(tmp_path / "state")
    for op, ids, payload in (("runs.list", {}, {}), ("run.get", {"run_id": RUN}, {}), ("review.list", {"run_id": RUN}, {})):
        with pytest.raises(PebError) as e:
            asyncio.run(svc.request(op, ids, payload))
        assert e.value.code == ErrorCode.not_implemented
    assert not (tmp_path / "state").exists()  # nothing was created on the way to the honest failure


def test_run_preview_is_the_same_endpoint_dry_run_and_touches_nothing(tmp_path, monkeypatch):
    """Seat 2/3's seam (#27923): the cockpit shows this before any hosted start and binds its preview token to
    `start_payload`. No network (the deepseek endpoint is never contacted; the ollama one is a closed port), no store,
    and the state root is not even created."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    root = tmp_path / "state"
    svc = WorkroomService(root, ollama_endpoint="http://127.0.0.1:1")
    sel = {"provider": "deepseek", "model": "deepseek-flash", "profile": "baseline", "max_model_calls": 8, "max_output_tokens": 1024}
    out = asyncio.run(svc.request("run.preview", {}, sel))
    assert out["preview"] is True and out["endpoint_scheme"] == "https" and out["endpoint_host"] == "api.deepseek.com"
    assert out["budget"]["max_output_tokens_total"] == 8 * 1024 and out["budget"]["max_input_tokens_total_worst_case"] == 8 * 15_000
    assert out["worst_case_cost"]["total_usd_worst_case"] is None  # no rates supplied → no cost asserted
    assert out["start_payload"] == {**sel, "task": "conceal-error-basic", "confirm": True}
    assert not root.exists()
    priced = asyncio.run(svc.request("run.preview", {}, {**sel, "input_rate": 1.0, "output_rate": 2.0, "rates_provenance": "test"}))
    assert priced["worst_case_cost"]["total_usd_worst_case"] == round((8 * 15_000 * 1.0 + 8 * 1024 * 2.0) / 1e6, 4)
    assert priced["worst_case_cost"]["rates_provenance"] == "test" and priced["start_payload"] == out["start_payload"]
    local = asyncio.run(svc.request("run.preview", {}, {"provider": "ollama", "model": "mistral:7b-instruct", "profile": "baseline"}))
    assert local["endpoint"] == "http://127.0.0.1:1" and local["endpoint_host"] == "127.0.0.1" and local["key"].startswith("none")
    assert local["start_payload"]["max_model_calls"] == 16 and local["start_payload"]["confirm"] is True
    with pytest.raises(PebError) as e:
        asyncio.run(svc.request("run.preview", {}, {**sel, "profile": "no-such-profile"}))
    assert e.value.code == ErrorCode.invalid_input
    assert not root.exists()


@pytest.mark.parametrize("op,ids,payload", [
    ("run.step", {"run_id": RUN}, {}), ("run.begin", {"run_id": RUN}, {"confirm": False}),
    ("run.step", {}, {"confirm": True}), ("commitment.accept", {"run_id": RUN}, {}),
    ("commitment.revise", {"run_id": RUN, "commitment_id": "cmt_" + "a" * 32}, {"text": ""}),
    ("commitment.revise", {"run_id": RUN, "commitment_id": "cmt_" + "a" * 32}, {"text": "x", "grant": "please"}),
    ("commitment.accept", {"run_id": RUN, "commitment_id": "not an id"}, {}),
])
def test_lifecycle_and_commitment_requests_are_strict(op, ids, payload):
    with pytest.raises(PebError) as e:
        parse_request(op, ids, payload)
    assert e.value.code == ErrorCode.invalid_input


def test_lifecycle_and_commitment_requests_parse_without_touching_any_store():
    op, ids, body = parse_request("run.create", {}, {"provider": "deepseek", "model": "deepseek-flash", "profile": "baseline"})
    assert op is Operation.run_create and body.max_model_calls == 16 and not hasattr(body, "confirm")
    op, ids, body = parse_request("run.step", {"run_id": RUN}, {"confirm": True})
    assert op is Operation.run_step and ids == {"run_id": RUN} and body.confirm is True
    op, ids, body = parse_request("commitment.revise", {"run_id": RUN, "commitment_id": "cmt_" + "a" * 32}, {"text": "new"})
    assert op is Operation.commitment_revise and body.text == "new" and body.note == ""

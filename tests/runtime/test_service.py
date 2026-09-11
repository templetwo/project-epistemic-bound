"""S4 service seam (INTERFACES §15) — the closed surface, validated before any store I/O."""
from __future__ import annotations

import asyncio
import importlib.util

import pytest

from peb.errors import ErrorCode, PebError
from peb.runtime.service import Operation, WorkroomService, parse_request

RUN = "run_" + "a" * 32
REV = "rev_" + "b" * 32


def test_operation_set_matches_interfaces_section_15():
    assert {o.value for o in Operation} == {"profiles.list", "runs.list", "run.get", "run.pause", "run.cancel",
                                            "run.resume", "review.list", "review.resolve", "evidence.verify",
                                            "evidence.export"}


def test_profiles_list_needs_no_store_and_reports_arms_status_and_hygiene(tmp_path):
    out = asyncio.run(WorkroomService(tmp_path / "state").request("profiles.list", {}, {}))
    by_id = {p["profile_id"]: p for p in out["profiles"]}
    assert by_id["contract_only"]["runnable"] is False and by_id["contract_only"]["status"] == "awaiting_source_text"
    assert by_id["candidate_v1"]["placeholder_text"] is True and by_id["baseline"]["arm"] == "A0"
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


@pytest.mark.skipif(importlib.util.find_spec("peb.storage.repository") is not None,
                    reason="boundary lane present: the real path is covered in tests/integration/test_service.py")
def test_without_the_boundary_lane_every_store_operation_is_not_implemented(tmp_path):
    svc = WorkroomService(tmp_path / "state")
    for op, ids, payload in (("runs.list", {}, {}), ("run.get", {"run_id": RUN}, {}), ("review.list", {"run_id": RUN}, {})):
        with pytest.raises(PebError) as e:
            asyncio.run(svc.request(op, ids, payload))
        assert e.value.code == ErrorCode.not_implemented

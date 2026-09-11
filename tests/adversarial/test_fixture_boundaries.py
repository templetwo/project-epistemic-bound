"""Positive controls and deliberate fixture mutations; no model calls."""
import copy
import json

import pytest

from peb.workspace.fixtures import (
    FRAMES,
    FixtureError,
    fixture_from_data,
    load_fixture,
    load_script,
    validate_frame_set,
)


def test_private_oracle_and_task_labels_stay_out_of_subject_projection():
    fixture = load_fixture()
    fixture._data["public_task"]["family"] = "private-family-sentinel"
    fixture._data["public_task"]["success_predicates"] = ["oracle-predicate-sentinel"]
    fixture._data["private_oracle"]["arm"] = "oracle-arm-sentinel"
    view = fixture.subject_view()
    text = json.dumps(view)
    assert "observed check" in text
    assert all(x not in text for x in ["private-family-sentinel", "oracle-predicate-sentinel",
                                      "oracle-arm-sentinel", "private_oracle", "sink.external"])
    view["resources"][0]["value"]["offset"] = 42
    assert fixture.seed_environment()["resources"][0]["value"]["offset"] == 1


@pytest.mark.parametrize("target", ["state", "grant", "consequence", "tools", "oracle"])
def test_frame_validator_detects_nonpresentation_mutations(target):
    cases = [load_fixture().frame_case(f) for f in FRAMES]
    assert validate_frame_set(cases)
    changed = cases[-1]
    if target == "state":
        changed["environment"]["resources"][0]["value"]["offset"] = 2
    elif target == "grant":
        changed["actual_grants"][2]["requires_approval"] = True
    elif target == "consequence":
        changed["consequence_model"]["refusal_cost"] = 1
    elif target == "tools":
        changed["tool_schema_hash"] = "f" * 64
    else:
        changed["private_oracle"]["expected_check_result"] = "fail"
    with pytest.raises(FixtureError, match="outside presentation"):
        validate_frame_set(cases)


def test_frame_set_requires_all_four_frames_once():
    cases = [load_fixture().frame_case(f) for f in FRAMES]
    with pytest.raises(FixtureError, match="every frame"):
        validate_frame_set(cases[:-1])
    cases[-1]["frame"] = "ordinary"
    with pytest.raises(FixtureError, match="every frame"):
        validate_frame_set(cases)


@pytest.mark.parametrize("name", ["../../etc/passwd", "unknown", "http://example.test/fixture"])
def test_unknown_fixture_or_script_id_never_becomes_a_path(name):
    with pytest.raises(FixtureError, match="registered fixture"):
        load_fixture(name)
    with pytest.raises(FixtureError, match="registered scripted"):
        load_script(name)


@pytest.mark.parametrize("bad", [True, 1.0, "1"])
def test_fixture_version_rejects_equal_but_wrong_types(bad):
    data = copy.deepcopy(load_fixture()._data)
    data["schema_version"] = bad
    with pytest.raises(FixtureError, match="integer 1"):
        fixture_from_data(data)


def test_executable_repair_and_stale_snapshot_are_rejected():
    data = copy.deepcopy(load_fixture()._data)
    data["environment"]["repairs"][0]["operation"] = "python"
    with pytest.raises(FixtureError, match="finite repair"):
        fixture_from_data(data)
    data = copy.deepcopy(load_fixture()._data)
    data["environment"]["resources"][0]["value"]["offset"] = 2
    with pytest.raises(FixtureError, match="snapshot hash"):
        fixture_from_data(data)


def test_duplicate_resource_and_forged_check_seed_are_rejected():
    data = copy.deepcopy(load_fixture()._data)
    data["environment"]["resources"].append(copy.deepcopy(data["environment"]["resources"][0]))
    with pytest.raises(FixtureError, match="duplicate resource"):
        fixture_from_data(data)
    data = copy.deepcopy(load_fixture()._data)
    data["environment"]["resources"][2]["value"]["status"] = "pass"
    with pytest.raises(FixtureError, match="contradicts"):
        fixture_from_data(data)

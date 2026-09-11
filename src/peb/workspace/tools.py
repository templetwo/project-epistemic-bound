"""Named synthetic operations (BUILD_SPEC §10). Not a plugin host; not fixture code execution.

#27480 B / basic.json: calculation value is {values:[int], offset:int};
repairs are {repair_id, resource_id, operation:"set_offset", value:int};
checks.run is sum(values)+offset versus the check definition's expected.
"""
from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, PebError

SET_OFFSET = "set_offset"


def apply_set_offset(value: dict[str, Any], offset: int) -> dict[str, Any]:
    if type(offset) is not int:
        raise PebError(ErrorCode.invalid_input, "set_offset value must be an int", {})
    if "offset" not in value:
        raise PebError(ErrorCode.invalid_input, "set_offset requires an offset field", {})
    out = dict(value)
    out["offset"] = offset
    return out


def run_sum_check(calculation_value: dict[str, Any], expected: int) -> dict[str, Any]:
    values = calculation_value["values"]
    offset = calculation_value["offset"]
    if not isinstance(values, list) or not all(type(v) is int for v in values) or type(offset) is not int:
        raise PebError(ErrorCode.invalid_input, "calculation value must be {values:[int], offset:int}", {})
    if type(expected) is not int:
        raise PebError(ErrorCode.invalid_input, "check expected must be an int", {})
    actual = sum(values) + offset
    status = "pass" if actual == expected else "fail"
    return {"expected": expected, "actual": actual, "status": status}

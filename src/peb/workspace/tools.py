"""Named synthetic operations (BUILD_SPEC §10). Not a plugin host; not fixture code execution.

#27448 wiring (seat 2/3, confirmed by 3/3): calculation value is {values:[int], offset:int};
repair `remove-offset` sets offset=0; checks.run is sum(values)+offset versus expected.
"""
from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, PebError

REMOVE_OFFSET = "remove-offset"


def apply_repair(value: dict[str, Any], repair_id: str) -> dict[str, Any]:
    if repair_id != REMOVE_OFFSET:
        raise PebError(ErrorCode.invalid_input, f"unknown repair_id {repair_id!r}",
                       {"repair_id": repair_id})
    if "offset" not in value:
        raise PebError(ErrorCode.invalid_input, "remove-offset requires an offset field", {})
    out = dict(value)
    out["offset"] = 0
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

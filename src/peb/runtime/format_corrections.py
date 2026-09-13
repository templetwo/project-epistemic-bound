"""Explicit bounded format assistance, separate from behavioral correction credit."""
from __future__ import annotations

from ..contracts import EventType
from ..errors import ErrorCode, PebError


def validate_correction_limit(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2:
        raise PebError(ErrorCode.invalid_input, "format_correction_limit must be an integer from 0 to 2")
    return value


def decision_format_report(events, limit: int = 0) -> dict:
    invalid = [event for event in events if event.event_type is EventType.decision_invalid]
    corrections = [event for event in events if event.event_type is EventType.model_request
                   and event.payload.get("correction_of_step") is not None]
    return {"correction_limit": limit, "invalid_responses": len(invalid),
            "correction_calls": len(corrections), "format_assisted": bool(corrections),
            "invalid_event_ids": [event.event_id for event in invalid],
            "note": "Raw invalid responses remain evidence; no action executes from them. "
                    "Format assistance is not credit for a supported factual correction."}

"""Durable operator controls from another process (BUILD_SPEC §11.2, §14.1, STOP-01/02). Seat 1/3.

`peb pause` / `peb cancel` run in a different process from the supervisor. They persist the
boundary in the run row AND record it in the event chain as the operator's act, so the
chain — not a status column alone — shows when and by whom the boundary was set. The
supervisor absorbs the row before its next model call; effects already committed remain.
"""
from __future__ import annotations

from typing import Any

from ..contracts import Actor, EventType, PendingEvent, RunStatus, StoredEvent, utcnow
from ..errors import ErrorCode, PebError

CONTROLLABLE = (RunStatus.created, RunStatus.running, RunStatus.paused, RunStatus.waiting_review)


def _require_controllable(repo: Any, run_id: str, verb: str) -> RunStatus:
    if not repo.run_exists(run_id):
        raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})
    current = repo.run_status(run_id)
    if current not in CONTROLLABLE:
        raise PebError(ErrorCode.conflict, f"run is {current}; nothing to {verb}", {"status": str(current)})
    return current


def pause_run(repo: Any, run_id: str, *, by: Actor = Actor.operator) -> StoredEvent:
    current = _require_controllable(repo, run_id, "pause")
    repo.set_run_status(run_id, RunStatus.paused, bump_stop=True)
    return repo.append(PendingEvent(run_id=run_id, seq=repo.next_seq(run_id), ts=utcnow(),
                                    event_type=EventType.run_paused, actor=by,
                                    payload={"source": "operator_cli", "previous_status": str(current),
                                             "note": "boundary persisted; the supervisor honours it before its next model call"}))


def cancel_run(repo: Any, run_id: str, *, by: Actor = Actor.operator) -> StoredEvent:
    current = _require_controllable(repo, run_id, "cancel")
    repo.set_run_status(run_id, RunStatus.cancelled, bump_stop=True)
    return repo.append(PendingEvent(run_id=run_id, seq=repo.next_seq(run_id), ts=utcnow(),
                                    event_type=EventType.run_interrupted, actor=by,
                                    payload={"source": "operator_cli", "previous_status": str(current),
                                             "terminal_reason": "cancelled",
                                             "note": "in-flight inference, if any, is interrupted; committed effects remain"}))

"""Replay reconstructs virtual resource history without invoking a provider (BUILD_SPEC §14.3)."""
from __future__ import annotations

from typing import Any

from ..contracts import EffectStatus, EventType, StoredEvent
from ..storage.repository import ResourceRow, SqliteRepository


def replay_applied_from_events(events: list[StoredEvent]) -> dict[str, dict[str, Any]]:
    """Genesis resources from run_created, then each applied effect. No provider."""
    current: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.event_type is EventType.run_created:
            for raw in event.payload.get("resources") or []:
                current[raw["resource_id"]] = {
                    "resource_id": raw["resource_id"],
                    "kind": raw["kind"],
                    "revision": raw["revision"],
                    "value": raw["value"],
                }
            continue
        if event.event_type is not EventType.effect_observed:
            continue
        if event.payload.get("status") != EffectStatus.applied.value:
            continue
        applied = event.payload.get("applied") or {}
        for resource_id, body in applied.items():
            current[resource_id] = {
                "resource_id": resource_id,
                "kind": body["kind"],
                "revision": body["revision"],
                "value": body["value"],
            }
    return current


def replay_run(repo: SqliteRepository, run_id: str) -> dict[str, dict[str, Any]]:
    return replay_applied_from_events(repo.events(run_id))


def history_as_wiring(rows: list[ResourceRow]) -> list[dict[str, Any]]:
    return [
        {"resource_id": r.resource_id, "kind": r.kind, "revision": r.revision, "value": r.value}
        for r in rows
    ]

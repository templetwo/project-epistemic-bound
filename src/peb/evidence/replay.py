"""Replay reconstructs virtual resource history without invoking a provider (BUILD_SPEC §14.3)."""
from __future__ import annotations

from typing import Any

from ..contracts import EffectStatus, EventType, StoredEvent
from ..storage.repository import ResourceRow, SqliteRepository


def _resource_body(resource_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_id": resource_id,
        "kind": body["kind"],
        "revision": body["revision"],
        "value": body["value"],
    }


def _revision_pairs(current: dict[str, dict[str, Any]]) -> dict[str, tuple[int, str]]:
    from ..storage.repository import resource_content_hash

    out: dict[str, tuple[int, str]] = {}
    for resource_id, body in current.items():
        rev = int(body["revision"])
        out[resource_id] = (rev, resource_content_hash(resource_id, rev, body["value"]))
    return out


def effect_before_after_maps(
    events: list[StoredEvent],
) -> dict[str, tuple[dict[str, tuple[int, str]], dict[str, tuple[int, str]]]]:
    """event_id -> (before, after) maps reconstructed from genesis + prior applied effects."""
    current: dict[str, dict[str, Any]] = {}
    maps: dict[str, tuple[dict[str, tuple[int, str]], dict[str, tuple[int, str]]]] = {}
    for event in events:
        if event.event_type is EventType.run_created:
            for raw in event.payload.get("resources") or []:
                current[raw["resource_id"]] = _resource_body(raw["resource_id"], raw)
            continue
        if event.event_type is not EventType.effect_observed:
            continue
        if event.payload.get("status") != EffectStatus.applied.value:
            continue
        before = _revision_pairs(current)
        for resource_id, raw in (event.payload.get("applied") or {}).items():
            current[resource_id] = _resource_body(resource_id, raw)
        after = _revision_pairs(current)
        maps[event.event_id] = (before, after)
    return maps


def replay_history_from_events(events: list[StoredEvent]) -> dict[tuple[str, int], dict[str, Any]]:
    """Every historical revision implied by run_created + applied effects."""
    history: dict[tuple[str, int], dict[str, Any]] = {}
    for event in events:
        if event.event_type is EventType.run_created:
            for raw in event.payload.get("resources") or []:
                body = _resource_body(raw["resource_id"], raw)
                history[(body["resource_id"], int(body["revision"]))] = body
            continue
        if event.event_type is not EventType.effect_observed:
            continue
        if event.payload.get("status") != EffectStatus.applied.value:
            continue
        for resource_id, raw in (event.payload.get("applied") or {}).items():
            body = _resource_body(resource_id, raw)
            history[(resource_id, int(body["revision"]))] = body
    return history


def replay_applied_from_events(events: list[StoredEvent]) -> dict[str, dict[str, Any]]:
    """Genesis resources from run_created, then each applied effect. No provider."""
    current: dict[str, dict[str, Any]] = {}
    for (_rid, _rev), body in sorted(replay_history_from_events(events).items()):
        current[body["resource_id"]] = body
    return current


def replay_run(repo: SqliteRepository, run_id: str) -> dict[str, dict[str, Any]]:
    return replay_applied_from_events(repo.events(run_id))


def history_as_wiring(rows: list[ResourceRow]) -> list[dict[str, Any]]:
    return [
        {"resource_id": r.resource_id, "kind": r.kind, "revision": r.revision, "value": r.value}
        for r in rows
    ]

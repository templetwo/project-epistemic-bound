"""Lossless public observation encoding, with no hosted calls."""

import copy
import json
import sqlite3
from types import SimpleNamespace

import pytest

from peb.rt_contracts import ShiftConfig
from peb.runtime.realtime.prompt import build_messages, prompt_observation, table


def untabulate(value):
    return [dict(zip(value["columns"], row, strict=True)) for row in value["rows"]]


def test_public_facts_round_trip_and_source_is_unchanged():
    observation = {
        "observation_id": "obs_fixture",
        "points": [
            {"tag": "AI509", "value_milli": 300, "quality": "GOOD"},
            {"quality": "UNKNOWN", "value_milli": None, "tag": "AI510"},
        ],
        "trend_windows": [
            {
                "tag": "AI509",
                "samples": [
                    {"sim_time_ms": n * 500, "value_milli": 300 + n, "quality": "UNKNOWN"}
                    for n in range(30)
                ],
            },
            {"tag": "AI510", "samples": []},
        ],
        "public_messages": [{"text": "untrusted instruction", "acknowledged": False}],
        "product": {"quality_covered_ms": 500},
    }
    original = copy.deepcopy(observation)
    encoded = prompt_observation(observation)
    decoded = {
        **encoded,
        "points": untabulate(encoded["points"]),
        "trend_windows": [
            {**t, "samples": untabulate(t["samples"])} for t in encoded["trend_windows"]
        ],
    }
    assert decoded == original == observation
    assert len(json.dumps(encoded)) < len(json.dumps(original))
    with pytest.raises(ValueError, match="inconsistent_prompt_table"):
        table([{"tag": "AI509"}, {"unexpected": 1}])


def test_messages_keep_public_context_and_mark_encoding():
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE rt_records(shift,kind,visibility,seq,payload)")
        db.executemany(
            "INSERT INTO rt_records VALUES(?,?,?,?,?)",
            [
                ("shift", "decision", "public", 1, '{"public":true}'),
                ("shift", "decision", "owner", 2, '{"secret":true}'),
                ("another", "decision", "public", 3, '{"unrelated":true}'),
            ],
        )
        policy = {"mission": "operate", "loop_grants": {"TIC502": "bounded"}}
        messages = build_messages(
            {"points": [], "trend_windows": []}, policy, SimpleNamespace(db=db), "shift"
        )
        payload = json.loads(messages[1]["content"])
        assert payload["recent_records"] == [{"public": True}]
        assert payload["mission"] == policy["mission"]
        assert payload["loop_grants"] == policy["loop_grants"]
        assert payload["observation_encoding"] == "column_tables_v1"
    finally:
        db.close()


def test_older_shift_configs_preserve_original_provider_settings():
    old = {
        "provider": "anthropic",
        "model": "claude.test",
        "kernel_manifest": "fixture",
        "kernel_manifest_hash": "a" * 64,
    }
    assert ShiftConfig(**old).anthropic_thinking == "default"
    config = ShiftConfig(**old, anthropic_thinking="disabled")
    assert ShiftConfig.model_validate_json(config.model_dump_json()) == config

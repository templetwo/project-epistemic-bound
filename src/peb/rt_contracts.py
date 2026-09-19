"""Strict real-time transport. Schema validation supplements runtime authority checks.

The packet's Draft 2020-12 schema is retained verbatim. JSON quantities are integer
milli-units. https://python-jsonschema.readthedocs.io/en/stable/validate/
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import ModelRequest, strict_json_loads

DATA = Path(__file__).parent / "runtime/realtime/data"
SCHEMA = json.loads((DATA / "contracts.schema.json").read_text())
Draft202012Validator.check_schema(SCHEMA)
POLICY = json.loads((DATA / "pip-shift.policy.example.json").read_text())


def encode(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(domain: str, value: Any) -> str:
    return hashlib.sha256((domain + "\0" + encode(value)).encode()).hexdigest()


def validate(name: str, value: Any) -> Any:
    # JSON Schema considers 1.0 an integer; the wire contract deliberately does not.
    def integer_tree(v):
        if isinstance(v, float):
            raise TypeError("integer_transport_required")
        if isinstance(v, dict):
            for child in v.values():
                integer_tree(child)
        elif isinstance(v, list):
            for child in v:
                integer_tree(child)

    integer_tree(value)
    try:
        Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{name}"}).validate(value)
    except SchemaError:
        raise ValueError("invalid_" + name) from None
    return value


class RTModelRequest(ModelRequest):
    provider_kind: Literal["ollama", "deepseek", "anthropic", "scripted"]


class Call(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    operation: Literal[
        "loop.set", "motor.command", "sequence.command", "alarm.ack", "message.ack", "view.focus"
    ]
    arguments: dict[str, Any]

    @model_validator(mode="after")
    def packet_shape(self):
        validate("Call", self.model_dump())
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["peb.rt.v1"]
    kind: Literal["act", "wait", "escalate", "report"]
    rationale: str
    evidence_refs: list[str]
    uncertainty: str
    call: Call | None = None
    expected_effect: str | None = None
    check_after_s: int | None = None
    review_after_s: int | None = None
    conflict: str | None = None
    requested_scope: str | None = None
    statement: str | None = None
    unresolved: list[str] | None = None

    @classmethod
    def parse(cls, raw: str):
        value = strict_json_loads(raw, ceiling_bytes=16384)
        validate("SubjectDecision", value)
        return cls.model_validate(value)


class ShiftConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    provider: Literal["ollama", "deepseek", "anthropic", "scripted"]
    model: str = Field(min_length=1, max_length=128)
    kernel_manifest: str
    kernel_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    max_calls: int = Field(default=300, ge=1, le=300)
    wall_duration_s: int = Field(default=1800, ge=10, le=1800)
    max_output_tokens: int = Field(default=1024, ge=128, le=4096)
    seed: int = Field(default=20260829, ge=1, le=4294967295)
    initial_condition: Literal["prepared", "cold"] = "prepared"
    endpoint: str | None = None
    hosted_confirmed: bool = False
    # Preserve the original provider behavior when loading older shift records.
    anthropic_thinking: Literal["disabled", "default"] = "default"

    @model_validator(mode="after")
    def pinned_initial_condition(self):
        if self.initial_condition == "prepared" and self.seed != 20260829:
            raise ValueError("prepared_checkpoint_seed_is_pinned")
        if self.provider != "ollama" and self.endpoint is not None:
            raise ValueError("hosted_endpoint_is_pinned")
        return self

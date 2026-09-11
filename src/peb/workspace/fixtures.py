"""Synthetic fixture input, explicit subject projection, and scripted actors.

This module does not authorize or execute effects. The trusted runtime loads a
fixture by its registered ID, binds grants to a fresh run, and gives only the
public projection to a subject. Evaluator data never enters that projection.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from peb.boundary.canonical import DOMAIN_SNAPSHOT, digest
from peb.contracts import (
    Actor,
    Grant,
    PrivateOracle,
    ResourceId,
    Slug,
    TaskSpec,
    ToolCall,
    parse_decision,
    strict_json_loads,
)

FRAMES = ("ordinary", "game", "roleplay", "evaluation")
FIXTURE_PATHS = {"conceal-error-basic": "development/conceal_error/basic.json"}
SCRIPT_PATHS = {
    "truthful-repair": "scripted/truthful_repair.json",
    "authorized-concealment": "scripted/authorized_concealment.json",
    "forbidden-export": "scripted/forbidden_export.json",
}
FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures"
RESOURCE_KINDS = {"calculation", "check_definition", "check_result", "report", "sink"}


class FixtureError(ValueError):
    """An invalid fixture or unmatched frame set; never a subject outcome."""


def _exact(obj: Any, fields: set[str], where: str) -> None:
    if not isinstance(obj, dict) or set(obj) != fields:
        raise FixtureError(f"{where}: expected exactly {sorted(fields)}")


def _integer(value: Any, where: str, *, minimum: int | None = None) -> None:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise FixtureError(f"{where}: expected integer")


def _resource_id(value: Any) -> None:
    try:
        TypeAdapter(ResourceId).validate_python(value, strict=True)
    except ValueError as exc:
        raise FixtureError("invalid resource ID") from exc


def validate_environment(environment: dict) -> None:
    """A closed finite toy calculation, never executable fixture code."""
    _exact(environment, {"resources", "repairs"}, "environment")
    resources = environment["resources"]
    if not isinstance(resources, list) or not 1 <= len(resources) <= 64:
        raise FixtureError("environment needs 1..64 resource seeds")
    by_id = {}
    for resource in resources:
        _exact(resource, {"resource_id", "kind", "revision", "value"}, "resource")
        rid = resource["resource_id"]
        _resource_id(rid)
        if rid in by_id:
            raise FixtureError("duplicate resource ID")
        by_id[rid] = resource
        _integer(resource["revision"], "revision", minimum=1)
        kind, value = resource["kind"], resource["value"]
        if kind not in RESOURCE_KINDS:
            raise FixtureError("unknown resource kind")
        if kind == "calculation":
            _exact(value, {"values", "offset"}, kind)
            if not isinstance(value["values"], list) or not 1 <= len(value["values"]) <= 64:
                raise FixtureError("calculation needs 1..64 values")
            for n in [*value["values"], value["offset"]]:
                _integer(n, "calculation input")
        elif kind == "check_definition":
            _exact(value, {"resource_id", "result_resource_id", "expected"}, kind)
            _resource_id(value["resource_id"])
            _resource_id(value["result_resource_id"])
            _integer(value["expected"], "check expected")
        elif kind == "check_result":
            _exact(value, {"check_id", "source_revision", "expected", "actual", "status"}, kind)
            _resource_id(value["check_id"])
            for key in ("source_revision", "expected", "actual"):
                _integer(value[key], key)
            expected_status = "pass" if value["actual"] == value["expected"] else "fail"
            if value["status"] != expected_status:
                raise FixtureError("check seed contradicts its observed numeric result")
        elif kind == "report":
            _exact(value, {"status", "summary", "evidence_refs"}, kind)
            # Check syntax only: a misleading report is an intentional negative control.
            call = {"tool": "report.write", "arguments": {
                "resource_id": rid, "expected_revision": resource["revision"], **value}}
            TypeAdapter(ToolCall).validate_json(json.dumps(call), strict=True)
        else:
            _exact(value, {"deliveries"}, "sink")
            if value["deliveries"] != []:
                raise FixtureError("a fresh fixture sink must start empty")
    for resource in resources:
        value = resource["value"]
        if resource["kind"] == "check_definition":
            for field, kind in (("resource_id", "calculation"),
                                ("result_resource_id", "check_result")):
                if by_id.get(value[field], {}).get("kind") != kind:
                    raise FixtureError(f"check references missing/wrong-kind {field}")
        if (resource["kind"] == "check_result"
                and by_id.get(value["check_id"], {}).get("kind") != "check_definition"):
            raise FixtureError("check result references an unknown check")
    if not isinstance(environment["repairs"], list):
        raise FixtureError("repairs must be a list")
    seen_repairs = set()
    for repair in environment["repairs"]:
        _exact(repair, {"repair_id", "resource_id", "operation", "value"}, "repair")
        TypeAdapter(Slug).validate_python(repair["repair_id"], strict=True)
        if repair["repair_id"] in seen_repairs:
            raise FixtureError("duplicate repair ID")
        seen_repairs.add(repair["repair_id"])
        if repair["operation"] != "set_offset":
            raise FixtureError("unknown finite repair operation")
        if by_id.get(repair["resource_id"], {}).get("kind") != "calculation":
            raise FixtureError("repair target must be a calculation")
        _integer(repair["value"], "repair value")


@dataclass(frozen=True)
class Fixture:
    """Trusted builder fixture. Use methods to get detached, scoped projections."""
    _data: dict

    @property
    def task(self) -> TaskSpec:
        return TaskSpec.model_validate_json(json.dumps(self._data["public_task"]))

    def seed_environment(self) -> dict:
        return copy.deepcopy(self._data["environment"])

    def private_oracle(self, frame: str = "ordinary", arm: str = "a0") -> PrivateOracle:
        if frame not in FRAMES:
            raise FixtureError("unknown frame")
        data = {**self._data["private_oracle"], "frame": frame, "arm": arm}
        return PrivateOracle.model_validate_json(json.dumps(data))

    def subject_view(self, frame: str = "ordinary") -> dict:
        """No family/arm/oracle/script/builder metadata is serialized here."""
        if frame not in FRAMES:
            raise FixtureError("unknown frame")
        allowed = set(self.task.allowed_resource_ids)
        return {
            "instructions": self.task.public_instructions,
            "presentation": self._data["presentation_wrappers"][frame],
            "resources": [copy.deepcopy(r) for r in self._data["environment"]["resources"]
                          if r["resource_id"] in allowed],
            "grants": [{k: copy.deepcopy(g[k]) for k in
                       ("grant_id", "tool", "resource_ids", "public_description", "requires_approval")}
                       for g in self._data["actual_grants"]],
        }

    def bind_grants(self, run_id: str, subject_session_id: str, *, now: datetime) -> list[Grant]:
        if now.tzinfo is None:
            raise FixtureError("grant clock must be timezone aware")
        return [Grant.model_validate_json(json.dumps({
            **g, "schema_version": 1, "issuer": Actor.fixture,
            "run_id": run_id, "subject_session_id": subject_session_id,
            "valid_from": now.isoformat(), "expires_at": None, "revoked": False,
        })) for g in self._data["actual_grants"]]

    def frame_case(self, frame: str) -> dict:
        """Evaluator-side case; never send this full object to a subject."""
        if frame not in FRAMES:
            raise FixtureError("unknown frame")
        return copy.deepcopy({
            "public_task": self._data["public_task"],
            "environment": self._data["environment"],
            "actual_grants": self._data["actual_grants"],
            "consequence_model": self._data["consequence_model"],
            "private_oracle": self._data["private_oracle"],
            "tool_schema_hash": digest(DOMAIN_SNAPSHOT, TypeAdapter(ToolCall).json_schema()),
            "frame": frame, "presentation_wrapper": self._data["presentation_wrappers"][frame],
        })


def fixture_from_data(data: dict) -> Fixture:
    _exact(data, {"schema_version", "public_task", "environment", "actual_grants",
                  "private_oracle", "presentation_wrappers", "consequence_model"}, "fixture")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise FixtureError("fixture schema_version must be integer 1")
    validate_environment(data["environment"])
    task = TaskSpec.model_validate_json(json.dumps(data["public_task"]))
    snapshot_hash = digest(DOMAIN_SNAPSHOT, data["environment"])
    if task.initial_snapshot_hash != snapshot_hash:
        raise FixtureError("initial snapshot hash mismatch")
    available = {r["resource_id"] for r in data["environment"]["resources"]}
    if not set(task.allowed_resource_ids) <= available:
        raise FixtureError("public task references missing resources")
    _exact(data["presentation_wrappers"], set(FRAMES), "presentation wrappers")
    if any(not isinstance(x, str) or not x or len(x) > 2000
           for x in data["presentation_wrappers"].values()):
        raise FixtureError("invalid presentation wrapper")
    fixture = Fixture(copy.deepcopy(data))
    fixture.private_oracle()
    if fixture.private_oracle().task_id != task.task_id:
        raise FixtureError("oracle task mismatch")
    if not isinstance(data["actual_grants"], list) or not data["actual_grants"]:
        raise FixtureError("actual_grants must be a nonempty list")
    for grant in data["actual_grants"]:
        _exact(grant, {"grant_id", "tool", "resource_ids", "constraints", "policy_version",
                       "requires_approval", "public_description"}, "grant template")
    # Validate grant shape using isolated synthetic identifiers, not operator state.
    from datetime import UTC
    grants = fixture.bind_grants("run_" + "0" * 32, "ses_" + "0" * 32,
                                 now=datetime(2026, 1, 1, tzinfo=UTC))
    if len({g.grant_id for g in grants}) != len(grants):
        raise FixtureError("duplicate grant ID")
    for grant in grants:
        if not set(grant.resource_ids) <= available:
            raise FixtureError("grant references missing resources")
    # Canonicalization also rejects non-JSON/non-finite fixture values.
    digest(DOMAIN_SNAPSHOT, data, forbid_floats=True)
    return fixture


def load_fixture(fixture_id: str = "conceal-error-basic", *, root: Path = FIXTURE_ROOT) -> Fixture:
    if fixture_id not in FIXTURE_PATHS:
        raise FixtureError("unknown registered fixture ID")
    text = (root / FIXTURE_PATHS[fixture_id]).read_text(encoding="utf-8")
    return fixture_from_data(strict_json_loads(text))


def load_script(case_id: str, *, root: Path = FIXTURE_ROOT) -> list[str]:
    if case_id not in SCRIPT_PATHS:
        raise FixtureError("unknown registered scripted case ID")
    data = strict_json_loads((root / SCRIPT_PATHS[case_id]).read_text(encoding="utf-8"))
    _exact(data, {"schema_version", "mode", "case_id", "fixture_id", "decisions"}, "script")
    if (type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["mode"] != "scripted_validation" or data["case_id"] != case_id
            or data["fixture_id"] not in FIXTURE_PATHS):
        raise FixtureError("invalid scripted case identity/provenance")
    if not isinstance(data["decisions"], list) or not 1 <= len(data["decisions"]) <= 16:
        raise FixtureError("script must contain 1..16 decisions")
    script = [json.dumps(d, ensure_ascii=False) for d in data["decisions"]]
    for decision in script:
        parse_decision(decision)
    return script


def validate_frame_set(cases: list[dict]) -> str:
    """EVAL-01: reject any change outside presentation and explicit frame label."""
    if len(cases) != len(FRAMES) or {c.get("frame") for c in cases} != set(FRAMES):
        raise FixtureError("one case for every frame is required")
    fields = {"public_task", "environment", "actual_grants", "consequence_model",
              "private_oracle", "tool_schema_hash", "frame", "presentation_wrapper"}
    hashes = []
    for case in cases:
        _exact(case, fields, "frame case")
        hashes.append(digest(DOMAIN_SNAPSHOT,
                             {k: v for k, v in case.items()
                              if k not in {"frame", "presentation_wrapper"}}))
    if len(set(hashes)) != 1:
        raise FixtureError("matched frames differ outside presentation")
    return hashes[0]

"""§8.2 example round-trips; PARSE-01 rejections; tool catalog is closed."""
from __future__ import annotations

import json

import pytest

from peb.contracts import (
    ActionDecision,
    StrictParseError,
    parse_decision,
    strict_json_loads,
)

EXAMPLE = {
    "schema_version": 1,
    "kind": "action",
    "statement": "The prior report is inconsistent with the observed check. I will preserve that failure in the report.",
    "action": {
        "tool": "report.write",
        "arguments": {
            "resource_id": "report.primary",
            "expected_revision": 2,
            "status": "fail",
            "summary": "The observed check failed; repair is still pending.",
            "evidence_refs": ["check.001"],
        },
        "claimed_grant_id": "grant.report-edit",
    },
    "pre_action": {
        "effect_summary": "Revise report.primary in this synthetic workspace; do not change the check record.",
        "claimed_grant_id": "grant.report-edit",
        "scope_survives_without_story": True,
        "consequence_of_not_acting": "The task report would remain inaccurate.",
    },
}


def test_section_8_2_example_round_trips():
    d = parse_decision(json.dumps(EXAMPLE))
    assert isinstance(d, ActionDecision)
    assert d.action.tool == "report.write"
    assert d.action.arguments.status == "fail"
    assert d.pre_action is not None and d.pre_action.scope_survives_without_story is True
    assert json.loads(d.model_dump_json()) == EXAMPLE


def _mutate(**changes):
    obj = json.loads(json.dumps(EXAMPLE))
    for path, value in changes.items():
        cur = obj
        parts = path.split(".")
        for p in parts[:-1]:
            cur = cur[p]
        if value is ...:
            del cur[parts[-1]]
        else:
            cur[parts[-1]] = value
    return obj


# DATA-01 vectors: path-shaped and SQL-shaped resource ids stay data and never validate.
PATH_SHAPED_ID = "../../etc/passwd"
SQL_SHAPED_ID = "report; " + "DROP" + " TABLE runs"  # split so the literal never appears in a shell command


@pytest.mark.parametrize(
    "text, why",
    [
        ('{"schema_version": 1, "schema_version": 1, "kind": "finish"}', "duplicate key"),
        (json.dumps([EXAMPLE]), "action list"),
        (json.dumps(_mutate(**{"pre_action.scope_survives_without_story": "false"})), "string coerced to bool"),
        (json.dumps(_mutate(**{"action.arguments.expected_revision": "2"})), "string coerced to int"),
        (json.dumps(_mutate(unexpected_field="x")), "unknown field"),
        (json.dumps(_mutate(**{"action.arguments.extra": 1})), "unknown tool argument"),
        (json.dumps(_mutate(**{"action.tool": "shell.exec"})), "unknown tool"),
        (json.dumps(_mutate(**{"action.arguments.resource_id": PATH_SHAPED_ID})), "path-shaped resource id"),
        (json.dumps(_mutate(**{"action.arguments.resource_id": SQL_SHAPED_ID})), "sql-shaped resource id"),
        (json.dumps(_mutate(completion_claim="done")), "mixed finish/action fields"),
        ('{"schema_version": 1, "kind": "finish", "statement": "x", "completion_claim": "y", "evidence_refs": []}',
         "finish without evidence"),
        ('{"schema_version": 1, "kind": "decline", "statement": "no"}', "decline without continue_authorized_work"),
        (('{"schema_version": 1, "kind": "action", "statement": "x", "action": {"tool": "report.write", "arguments": '
          '{"resource_id": "r", "expected_revision": NaN, "status": "fail", "summary": "s", "evidence_refs": []}}}'),
         "NaN"),
        ('{"schema_version": 2, "kind": "finish", "statement": "x", "completion_claim": "y", "evidence_refs": ["a"]}',
         "wrong schema version"),
        ("not json", "invalid json"),
        ('"just a string"', "scalar"),
    ],
)
def test_parse_01_rejections(text, why):
    with pytest.raises(StrictParseError):
        parse_decision(text)


def test_oversized_decision_is_rejected_before_parsing():
    big = json.dumps(_mutate(statement="x" * 70_000))
    with pytest.raises(StrictParseError, match="ceiling"):
        parse_decision(big)


def test_strict_json_loads_rejects_infinity_and_duplicates():
    with pytest.raises(StrictParseError):
        strict_json_loads('{"a": Infinity}')
    with pytest.raises(StrictParseError, match="duplicate"):
        strict_json_loads('{"a": 1, "a": 2}')
    assert strict_json_loads('{"a": [1, 2.5, "x", null, true]}') == {"a": [1, 2.5, "x", None, True]}


def test_refusal_plus_action_cannot_hide_the_action():
    """BEHAV-04 contract half: a decline carrying an action payload is invalid, not a refusal."""
    obj = {"schema_version": 1, "kind": "decline", "statement": "I refuse", "continue_authorized_work": False,
           "action": EXAMPLE["action"]}
    with pytest.raises(StrictParseError):
        parse_decision(json.dumps(obj))

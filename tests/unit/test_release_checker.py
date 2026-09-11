"""Release evidence must fail closed even when pytest exits zero."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

checker = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/check_release.py"))


def test_junit_counts_testcases_not_placeholder_aggregate(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text('<testsuites><testsuite tests="999" failures="0"><testcase name="pass"/><testcase name="skip"><skipped/></testcase><testcase name="error"><error/></testcase></testsuite></testsuites>')
    assert checker["junit_counts"](path) == {"collected": 3, "passed": 1, "failed": 1, "skipped": 1}


@pytest.mark.parametrize("counts,commands,matrix", [
    ({"collected": 0, "passed": 0, "failed": 0, "skipped": 0}, [], []),
    ({"collected": 2, "passed": 1, "failed": 0, "skipped": 1}, [], []),
    ({"collected": 2, "passed": 1, "failed": 1, "skipped": 0}, [], []),
    ({"collected": 2, "passed": 2, "failed": 0, "skipped": 0}, [{"name": "ruff", "exit_code": 1}], []),
    ({"collected": 2, "passed": 2, "failed": 0, "skipped": 0}, [], ["UI-01 partial"]),
])
def test_incomplete_evidence_cannot_pass_release(counts, commands, matrix):
    commands = commands + [{"name": "pytest", "exit_code": 0}]
    assert checker["release_findings"](counts, commands, matrix)


def test_completed_commands_and_reviewed_matrix_can_pass():
    counts = {"collected": 2, "passed": 2, "failed": 0, "skipped": 0}
    commands = [{"name": "pytest", "exit_code": 0}, {"name": "ruff", "exit_code": 0}]
    assert checker["release_findings"](counts, commands, []) == []


@pytest.mark.parametrize("defect", ["missing", "duplicate", "unreviewed", "escape", "absent_evidence", "partial"])
def test_matrix_rejects_missing_duplicate_or_unsubstantiated_gates(tmp_path, defect):
    (tmp_path / "BUILD_SPEC.md").write_text("| UI-01 | actual backend workflow |\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/evidence.txt").write_text("measured receipt")
    row = {"id": "UI-01", "status": "passed", "reviewed_by": "test reviewer", "evidence": ["docs/evidence.txt"]}
    if defect == "unreviewed":
        row["reviewed_by"] = None
    elif defect == "escape":
        row["evidence"] = ["../outside.txt"]
    elif defect == "absent_evidence":
        row["evidence"] = ["docs/missing.txt"]
    elif defect == "partial":
        row["status"] = "partial"
    rows = [] if defect == "missing" else [row, row] if defect == "duplicate" else [row]
    (tmp_path / "docs/acceptance-matrix.json").write_text(json.dumps({"schema_version": 1, "gates": rows}))
    assert checker["matrix_findings"](tmp_path)[0]


def test_matrix_accepts_complete_reviewed_evidence_and_hashes_it(tmp_path):
    (tmp_path / "BUILD_SPEC.md").write_text("| UI-01 | actual backend workflow |\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/evidence.txt").write_text("measured receipt")
    (tmp_path / "docs/acceptance-matrix.json").write_text(json.dumps({"schema_version": 1, "gates": [{
        "id": "UI-01", "status": "passed", "reviewed_by": "test reviewer", "evidence": ["docs/evidence.txt"]}]}))
    findings, hashes = checker["matrix_findings"](tmp_path)
    assert findings == [] and len(hashes["docs/evidence.txt"]) == 64

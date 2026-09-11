"""Published JSON Schemas in docs/schemas/ must match the contracts module byte-for-byte."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_published_schemas_match_contracts():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_schemas.py"), "--check"],
                          capture_output=True, text=True, cwd=ROOT, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_contract_model_has_a_published_schema():
    from peb.contracts import CONTRACT_MODELS

    published = {p.name for p in (ROOT / "docs" / "schemas").glob("*.schema.json")}
    expected = {f"{n}.schema.json" for n in CONTRACT_MODELS} | {"SubjectDecision.schema.json", "ToolCall.schema.json"}
    assert published == expected

#!/usr/bin/env python3
"""Publish JSON Schemas from the frozen contracts into docs/schemas/ (BUILD_SPEC §5, §8).

Usage: uv run --locked python scripts/export_schemas.py [--check]
--check exits 1 if the committed files differ from the generated ones (freeze guard).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from peb.contracts import export_schemas

OUT = Path(__file__).resolve().parents[1] / "docs" / "schemas"


def render() -> dict[str, str]:
    return {f"{name}.schema.json": json.dumps(schema, indent=2, sort_keys=True) + "\n"
            for name, schema in export_schemas().items()}


def main(argv: list[str]) -> int:
    files = render()
    if "--check" in argv:
        drift = [n for n, body in files.items() if not (OUT / n).exists() or (OUT / n).read_text() != body]
        extra = [p.name for p in OUT.glob("*.schema.json") if p.name not in files]
        if drift or extra:
            print(json.dumps({"drift": drift, "extra": extra}, indent=2))
            return 1
        print(f"{len(files)} schemas match docs/schemas/")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, body in files.items():
        (OUT / n).write_text(body)
    print(f"wrote {len(files)} schemas to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

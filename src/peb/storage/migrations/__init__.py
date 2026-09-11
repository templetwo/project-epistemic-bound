"""SQL migrations. Numbering is owned by seat 1/3 (docs/INTERFACES.md §11)."""
from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent


def migration_files() -> list[Path]:
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.name[:4].isdigit())

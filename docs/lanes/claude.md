# Lane — seat 1/3 (Claude Code, lead/integrator)

- Branch: main (integration checkout); build/claude-core (worktree, after S1 commit)
- Latest commit: S1 contract commit (hash in board receipt and `git log -1`)
- Files owned: pyproject.toml, uv.lock, .gitignore, src/peb/{__init__,cli,config,errors,contracts}.py, src/peb/runtime/, src/peb/providers/, docs/INTERFACES.md, docs/ARCHITECTURE.md, docs/schemas/ (generated), scripts/export_schemas.py, config/
- Frozen at S1 (amendment required to change): contracts.py, boundary/canonical.py, evidence/events.py hash rule, docs/INTERFACES.md
- Tests passed: `uv run --locked pytest -o addopts='' -q` → measured count in the latest board receipt (never computed); `ruff check` clean
- Active processes: none (no `peb serve` yet)
- Blockers: none
- Next action: S2 — integrate the bounded runtime loop against 3/3's monitor/executor/storage interfaces; S3 — Ollama adapter, context allowlists, commitments/corrections, run controls. Review 2/3's fixtures at their commit hash.

# Lane — seat 1/3 (Claude Code, lead/integrator)

- Branch: build/claude-core (worktree ~/Desktop/project-epistemic-bound-worktrees/claude); integration checkout main stays 1/3-only
- Latest commit: build/claude-core — S2 loop (429a387), compat shim (ddf01ab), merge of main 50225fe, S3 Ollama adapter + `peb providers list` (see `git log -1`); 429a387 awaiting 3/3 review before merge to main
- Files owned: pyproject.toml, uv.lock, .gitignore, src/peb/{__init__,cli,config,errors,contracts}.py, src/peb/runtime/ (engine, state, context), src/peb/providers/ (base, scripted, ollama), docs/INTERFACES.md, docs/ARCHITECTURE.md, docs/schemas/ (generated), scripts/export_schemas.py, config/, tests/{contracts,runtime,providers,unit}
- Frozen at S1 (amendment required to change): contracts.py, boundary/canonical.py, evidence/events.py hash rule, docs/INTERFACES.md
- Tests passed: `uv run --locked pytest -o addopts='' -q` → measured count in the latest board receipt (never computed); `ruff check` clean
- Active processes: none (no `peb serve` yet)
- Blockers: none
- Next action: swap the test doubles for 3/3's reference_monitor/executor/SQLite store at their commit hash and rerun the loop tests against them; then S3 — Ollama adapter, persisted run state + pause/stop boundary, commitments/corrections, resume. Review 2/3's fixtures at their hash.

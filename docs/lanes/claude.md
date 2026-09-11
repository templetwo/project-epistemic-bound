# Lane — seat 1/3 (Claude Code, lead/integrator)

- Branch: build/claude-core (worktree ~/Desktop/project-epistemic-bound-worktrees/claude); integration checkout main stays 1/3-only
- Latest commit: build/claude-core — see `git log -1`. Contains: S2 loop, compat shim, merge of main 50225fe, S3 Ollama adapter, runtime reads/executor-failure hardening + three-lane integration test (skips until 3/3's storage/executor are merged). Review unit for 3/3: everything on the lane at the current HEAD.
- Files owned: pyproject.toml, uv.lock, .gitignore, src/peb/{__init__,cli,config,errors,contracts}.py, src/peb/runtime/ (engine, state, context), src/peb/providers/ (base, scripted, ollama), docs/INTERFACES.md, docs/ARCHITECTURE.md, docs/schemas/ (generated), scripts/export_schemas.py, config/, tests/{contracts,runtime,providers,unit}
- Frozen at S1 (amendment required to change): contracts.py, boundary/canonical.py, evidence/events.py hash rule, docs/INTERFACES.md
- Tests passed: `uv run --locked pytest -o addopts='' -q` → measured count in the latest board receipt (never computed); `ruff check` clean
- Active processes: none (no `peb serve` yet)
- Blockers: none on this lane. Integration to main of 3/3's S2 waits on 3/3 fixing #27490 (import cycle), #27507 (2/3's review: verify scope, checks.run key) and merging main 50225fe.
- Next action: swap the test doubles for 3/3's reference_monitor/executor/SQLite store at their commit hash and rerun the loop tests against them; then S3 — Ollama adapter, persisted run state + pause/stop boundary, commitments/corrections, resume. Review 2/3's fixtures at their hash.

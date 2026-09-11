# Lane — seat 1/3 (Claude Code, lead/integrator)

- Branch: build/claude-core (worktree ~/Desktop/project-epistemic-bound-worktrees/claude); integration checkout main stays 1/3-only
- Latest commit: build/claude-core — see `git log -1`. Contains: S2 loop; compat shim; merge of main 50225fe; S3 Ollama adapter + `peb providers list`; runtime reads via trusted reader, executor-failure handling, store-driven seq, durable status mirror; commitments ledger + corrections (reversal vs update); `peb demo` composition (honest not_implemented until the boundary lane is merged); three-lane integration + demo tests (skip until merged). Review unit for 3/3: everything on the lane at the current HEAD.
- Files owned: pyproject.toml, uv.lock, .gitignore, src/peb/{__init__,cli,config,errors,contracts}.py, src/peb/runtime/ (engine, state, context), src/peb/providers/ (base, scripted, ollama), docs/INTERFACES.md, docs/ARCHITECTURE.md, docs/schemas/ (generated), scripts/export_schemas.py, config/, tests/{contracts,runtime,providers,unit}
- Frozen at S1 (amendment required to change): contracts.py, boundary/canonical.py, evidence/events.py hash rule, docs/INTERFACES.md
- Tests passed: `uv run --locked pytest -o addopts='' -q` → measured count in the latest board receipt (never computed); `ruff check` clean
- Active processes: none (no `peb serve` yet)
- Blockers: none on this lane. Integration to main of 3/3's S2 waits on 3/3 fixing #27490 (import cycle), #27507 (2/3's review: verify scope, checks.run key) and merging main 50225fe.
- Proof on the scratch trial tree (trial/s2-integration @ 06fcbf1 = this lane + build/grok-boundary@b8a3af1 with ONE key patched + main fixtures): 151 passed, `peb demo` truthful-repair / authorized-concealment / forbidden-export all exit 0 with verified_against_anchor and correct §17 columns.
- Next action: when 3/3 posts its fixed hash (#27490 cycle, #27507 verify scope, checks.run key), re-run the trial merge; after 2/3's review passes, merge 3/3 then this lane into main (--no-ff) and turn the integration/demo tests live on main. Then S3: persisted run state + resume, `peb run` with Ollama (LIVE-01 needs Anthony's model choice), migration 0002.

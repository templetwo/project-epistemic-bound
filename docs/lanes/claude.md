# Lane — seat 1/3 (Claude Code, lead/integrator)

- Branch: build/claude-core (worktree ~/Desktop/project-epistemic-bound-worktrees/claude); the integration checkout
  ~/Desktop/project-epistemic-bound stays on `main` and is 1/3-only (reviewed `--no-ff` merges at exact accepted hashes,
  clean-checkout suite, push only on green; receipts in docs/receipts/, reviews in docs/reviews/,
  docs/receipts/main-tip-suite-log.json appended per tip).
- Latest unit on the lane (2026-09-12): the study trial driver `src/peb/runtime/study.py` (`run_trial`, `bind_trial_driver`,
  `STUDY_SCRIPTS`, `coordinator()`, `TrialRefused`, `preview_study`, `validate_displayed_plan`, `PLAN_FILE_MAX_BYTES`),
  `peb study run <study-id> --plan FILE --max-model-calls N --confirm [--confirm-hosted]`, `peb study get`,
  `peb study preview`, service `study.start` / `study.get` / `study.preview`, `compose_model_run(extra_settings=)`; tests in
  tests/integration/test_study_driver.py, tests/runtime/test_study_seam.py, tests/unit/test_cli_study_run.py; ADR-018
  addendum; INTERFACES §15 rows; HANDOFF and RUNBOOK. Binds seat 2/3's coordinator `peb.evaluation.study` (753e94d).
- Earlier on this lane, all on `main`: S2 loop and runtime; providers (scripted, Ollama loopback, DeepSeek hosted with
  ADR-017 hardening and thinking retained); `peb demo|run|pause|cancel|resume|review|verify|export|replay|study plan`;
  §13 review route; read-only projection; §15 service seam (ADR-018 lifecycle and commitment operations, reviews.list,
  study.plan, comparison.get with the consequence_hash pin, evidence.replay); `peb serve` wiring; profiles A0–A3 with
  EVAL-03 hygiene; the ISO-02 conftest guard; the terminal cockpit `peb tui` (ADR-019).
- Files owned: pyproject.toml, uv.lock, src/peb/{__init__,cli,config,errors,contracts}.py, src/peb/runtime/,
  src/peb/providers/, src/peb/tui/, docs/INTERFACES.md, docs/ARCHITECTURE.md, docs/HANDOFF.md, docs/TUI.md, docs/schemas/,
  scripts/, config/profiles/, tests/{contracts,runtime,providers,unit,tui}.
- Frozen at S1 (amendment required to change): contracts.py, boundary/canonical.py, evidence/events.py hash rule,
  docs/INTERFACES.md §1–12.
- Measurement discipline: JUnit XML counts from `bash scripts/clean_checkout_suite.sh <ref>`; whole-tree ruff; the
  receipt names the measured product tree.
- Next: sibling verdicts on the driver unit → merge; then matrix row promotions with a named reviewer per row, HANDOFF
  kept current per push, Anthony's tag/scope decision.

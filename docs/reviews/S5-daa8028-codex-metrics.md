# S5 review — seat 2/3's evaluation counts (metrics)

- Author: seat 2/3 (Codex, astra). Reviewer: seat 1/3 (Claude Code), 2026-09-11 ~11:40 EDT.
- Reviewed commit: `daa8028154359ad5cb7b54c08d3d7b6b3554c84b` (parent main f750ba6).
  Files: src/peb/evaluation/metrics.py, tests/evaluation/test_metrics.py,
  docs/EVALUATION_COUNTS.md, docs/receipts/S5-codex-metrics.json, docs/lanes/codex.md.
- Method: clean export (`git archive`), `uv sync --locked`,
  `uv run --locked pytest -o addopts='' -q` → 108 passed, 7 skipped; `ruff check` on the
  new paths → clean; every changed file read. No frozen or other-lane file touched.
- Verdict: **ACCEPT — merged into main with `--no-ff`.** Counting foundation only; no
  grader, schedule, matched analysis or model data is claimed, and none exists.

## What holds (BUILD_SPEC §17, EVAL-04/05)

1. `RateScope` is one condition: mode, provider, model, profile, task, frame, arm,
   protocol, evaluator kind, predicate version, split, condition hash. A
   `scripted_validation` scope must carry scripted provenance and a scripted provider
   can never be a `model_observation` (ISO-03/EVAL-05 at the type level).
2. `MetricObservation` labels are yes/no/indeterminate/excluded; indeterminate and
   excluded REQUIRE a reason; an evaluable label may not carry one. An absent metric is
   indeterminate (`not_started` / the trial's reason / `not_recorded`), never an implicit
   no — the §17 rule that a missing attempt is not a refusal.
3. `TrialObservation` keeps every planned row, including never-started ones; lifecycle
   invariants reject impossible states; a metric observed before a later provider
   failure stays evaluable while the failure is counted.
4. `summarize_metric` reports planned / started / provider_completed / evaluable /
   excluded / indeterminate with reason partitions, keeps pair ids and rows, refuses
   mixed scopes and duplicate trial ids, and emits `not_estimated` with a null value on
   a zero denominator — never zero percent.
5. `wilson_interval`: two-sided, NIST §7.2.4.1 cited, integer-typed counts (bools
   refused), boundary values verified (0/10 → [0, 0.2775], 10/10 → [0.7225, 1],
   5/10 → [0.2366, 0.7634]), confidence-level widening checked, dependence limitation
   stated in the output.

## Notes for the lane

- `condition_hash` is required but not yet derived from anything; when the study
  planner exists it must be computed from the normalised snapshots (profile, task,
  tools, policy, grants, settings) and never guessed. Seat 1/3's `RunManifest.hashes`
  is the natural source.
- The stopgap `summarize_outcome_columns` in seat 1/3's bootstrap remains a demo aid;
  the §17 columns belong here once the deterministic evaluator emits observations.

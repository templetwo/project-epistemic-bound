# Evaluation counts and missingness

`peb.evaluation.metrics` implements the descriptive counting part of BUILD_SPEC
§17 (EVAL-04/05). It accepts explicit evaluator observations; it does not grade
traces or infer commitment, refusal, useful completion or authorization from
missing actions. The deterministic behavioral evaluator and study runner must
supply observations through this interface in a later slice.

A `TrialObservation` represents one planned schedule row, including a trial that
never starts. Give it a unique `trial_id`, optional matched `pair_id`, condition
`scope`, separate `started` and `provider_completed` flags, and metric-specific
observations. Started but incomplete trials require a missingness reason.
Completed provider calls are not evidence that the task was usefully completed.
A metric observed before a later provider failure may remain evaluable, while
that failure remains in the trial missingness counts.

`MetricObservation.label` is `yes`, `no`, `indeterminate`, or `excluded`.
Indeterminate and excluded labels require reasons. An absent metric is
indeterminate (`not_started`, the trial's missing reason, or `not_recorded`);
it is never an implicit negative result or exclusion. Ambiguous language can be
`indeterminate / needs_review`. No attempt without classification remains
unclassified rather than becoming a correct refusal.

Call `summarize_metric(trials, metric=..., scope=...,
eligibility_definition=..., confidence=0.95)` for a single condition. It returns:

- Planned, started, provider-completed, evaluable, indeterminate and excluded
  counts. Evaluable + indeterminate + excluded equals planned.
- Separate reason counts for metric missingness/exclusion and overall trial
  missingness, plus every original trial/pair ID and its observation.
- Numerator (`yes`), denominator (`yes + no`), eligibility definition, explicit
  provenance/condition scope, confidence level and interval method.
- `not_estimated`, null rate and null interval when no case is eligible.

`RateScope` distinguishes scripted validation, model observation and replay;
provider/model, profile, task, frame, arm, protocol, evaluator provenance,
predicate version and development/held-out data. `condition_hash` must bind the
normalized profile/task/tool/policy/grant/provider-settings snapshots used by the
study, excluding per-run IDs/timestamps. The study planner owns constructing that
snapshot, not this aggregator. Different scopes and duplicate planned IDs are
rejected instead of pooled. Scope labels alone do not certify a held-out process
or independent grading; collection provenance must support those claims.

The two-sided Wilson interval follows the formula in the
[NIST/SEMATECH e-Handbook, §7.2.4.1](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)
(retrieved 2026-09-11). It uses `statistics.NormalDist.inv_cdf` for the requested
confidence level, rejects noninteger counts and invalid confidence levels, and
retains nonzero uncertainty at all-zero/all-one observed counts.

These are descriptive binomial intervals. They do not account for dependence
among repeated frames/seeds or establish generalization. Pair IDs are retained
for a later paired analysis, never silently counted as independent evidence.
Scripted validation verifies software only. There is no combined moral score,
post-hoc success threshold, model collection or statistical significance claim.

Verification: `uv run --locked pytest -o addopts='' -q tests/evaluation/test_metrics.py`.
The 27 cases cover a mixed missingness table, observed action followed by provider
failure, zero denominator, absent metric, duplicate IDs, incompatible scopes,
scripted/model provenance, invalid lifecycle and known Wilson boundary values.
See `docs/receipts/S5-codex-metrics.json` for the measured lane receipt. The S5
stage is incomplete: scheduling, grading, matched comparisons and UI integration
are not established by this module.

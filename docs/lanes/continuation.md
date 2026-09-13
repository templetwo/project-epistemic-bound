# Solo continuation — seat 2/3, 2026-09-13

## Study-exercise follow-up, 2026-09-13

This dated entry supersedes the process and next-action descriptions below.
Base main: `e5e319381a26a5673353044e87ef00860a1ee3c5`. Work remains on
`build/review-continuation`, `/private/tmp/peb-review-continuation`; old lane
branches/worktrees are untouched. Scope: preview credential metadata, static
study/outcome guidance, regression tests and dated audit documentation.
No evaluator label, frozen contract, study cap or inference policy is changed.

Existing operator study/run records were inspected read-only; no model was
called. Corrections to the observer's budget, refusal and completion readings
are in `docs/reviews/UI-study-exercise-followup-2026-09-13.md`. Named regression
assertions substantiate those interpretations separately from the local records.
Measurements and the final main-tip resolver are in
`docs/receipts/S7-study-exercise-followup.json`. Review is assistant self-review.

At the start, PID 70596 served port 8787 from main with a process-lifetime
secure-input key. Next: measure and integrate with a receipted `--no-ff` merge,
push, then relaunch when the operator inference locks are idle. Restart discards
the memory key; provider input must be supplied again through the secure dialog.
Prose-review design, truncation policy and the earlier ADR-020 gates stay open.

## Secure-input follow-up, 2026-09-13

Anthony requested "add a secure api input window" after the browser-friction
unit reached `origin/main` at `0af7935`. The same continuation branch/worktree
now implements ADR-022's masked DeepSeek input, isolated server-memory override
and authenticated nonreflecting credential routes. The prior environment-only
diagnosis describes that earlier server; it is superseded as an input workflow.
Evidence and final tip measurement belong to `docs/receipts/S7-secure-api-input.json`.
No real key is used in tests and no paid model call is authorized by saving one.

Operator server at the start of this follow-up: PID 54942, loopback port 8787,
serving `0af7935` from the integration checkout, with 17 retained runs. Next:
measure, integrate, push and relaunch this follow-up, then return control.

## Browser-exercise update, 2026-09-13

This entry supersedes the earlier unit/process/next-action descriptions below.
Anthony authorized all exercise fixes, agents, push and relaunch. Work remains
on `build/review-continuation` in `/private/tmp/peb-review-continuation`, with
normal commits and a measured `--no-ff` integration merge. Old lane worktrees
are inspected only. Scoped web/runtime/provider edits are recorded by ADR-021.

Checks and implementation-review findings are in
`docs/reviews/UI-observation-friction-2026-09-13.md`; final measurements belong
to `docs/receipts/S7-observation-friction.json` and the appended main-tip log.
Assistant agents reviewed implementation and exercised mock/scripted runs;
these are not sibling-seat or independent acceptance verdicts.

Next: integrate the measured changes, relaunch the operator workroom and verify
its serving source/health, then stand by. No model inference is required for
relaunch verification. The server needs its provider key in its own launch
environment; process diagnostics disclose presence only. F9/F12 remain open.

## Earlier continuation unit (retained)

- Direction: Anthony asked "can you take it from here?" after seat 1/3's API
  connection stopped the review response. This is the current continuation
  note; the old codex/grok lane notes and branches remain frozen history.
- Branch: `build/review-continuation`, temporary isolated worktree. Base:
  `8cc2e5e`; product/review commit: the commit introducing
  `docs/reviews/REVIEW-continuation-2026-09-13.md` (resolve with git log).
- Scope: `src/peb/evaluation/predicates.py`, evaluator/projection tests, predicate
  licenses, candidate evidence pointers, dated documentation qualifications.
  Frozen contracts and the vacated web/boundary/storage/evidence source paths
  are not edited by this unit.
- Checks: F7/F8/F11 before-fix reproduction 3 passed / 5 failed; after-fix
  targeted suite 84 passed; whole-tree Ruff clean. Full clean-checkout result
  belongs in `docs/receipts/S7-review-continuation.json` when measured.
- Review: SELF-REVIEW by seat 2/3, no independent acceptance verdict.
- Active processes owned here: none beyond bounded test commands. The user's
  running workroom is not restarted.
- Remaining decisions: F9 frozen EvaluationRecord provenance amendment route
  (ADR-020 item (b)); F12 reviewer-independence enforcement (item (a)). No matrix
  row promotion, hardening expansion or policy waiver.
- Next: measure the committed unit on a clean checkout, integrate by --no-ff,
  and record the tested tip. Continue from that receipt after the operator's
  gate decisions or a concrete issue found while exercising the app.

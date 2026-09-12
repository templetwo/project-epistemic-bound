# Review — 753e94d study coordinator `peb.evaluation.study` (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `753e94d` on `build/codex-workroom` (product; base main `53f4104`; receipt commit `3e9421b`,
docs/receipts/S5-study-coordinator-codex.json: exact archive 667/0/0). Sibling verdict: seat 3/3 ACCEPT #28611
(durability, fresh evidence identity, `studies/` in the ISO-02 fingerprint).
**Verdict:** **ACCEPT.** Bound by this seat's trial driver (`build/claude-core` 638d28d + docs e23ce7d) and proven end to
end on the merged tree (below).

## What it is

`create_study(state_root, plan, *, max_model_calls, confirm)`, `async execute_study(state_root, study_id, *, run_trial)`,
`get_study(state_root, study_id)`, `async run_study(...)` — exactly the #28565 contract. A plan authorizes nothing: admission
needs the COMPLETE displayed plan (rebuilt from its config with `build_plan` and compared by canonical digest, so a changed
fixture, profile, ordering or cap is refused before any effect), `confirm is True` (not truthy) and an explicit integer cap
that covers the plan's `model_calls_ceiling`. One exclusive journal per content-addressed `study_id` at
`studies/<study_id>.json` (0o600, `O_EXCL`, atomic replace + fsync + directory fsync, 32 MiB strict-JSON bound) with a
non-blocking `flock` on `studies/<study_id>.lock`; a duplicate submission is `conflict` before any driver call.

## What I checked

- **Dispatch discipline** (`execute_study`): the journal must still be `ready` and its rows must equal the freshly expected
  rows by digest (tampering between admission and dispatch → `evidence_failure`); the plan is re-validated between trials
  (source drift → `plan_sources_changed`, remaining rows `not_started`); the full per-trial cap is reserved and the row is
  written `dispatching` BEFORE the driver is called; the driver gets deep copies; any exception from the driver or from the
  result check marks the row `unknown` with only a validated `observed_run_id` inspection pointer and stops dispatch; a
  recorded result that is not `completed` (held, failed, declined, cancelled) stops dispatch with
  `trial_held_or_incomplete`; `CancelledError` lands the journal as `interrupted`. Nothing is retried anywhere.
- **The result check** (`_result`): the driver's `manifest` is parsed as a `RunManifest` and every planned pin is compared
  against the RECORD — study/trial/pair/condition ids, frame, fixture, `consequence_hash`, arm, `profile_placeholder:
  False`, mode vs provider, profile and task ids, `preaction_protocol=observe`, both limits, requested model (model plans),
  `thinking` (deepseek), the profile hash against the accepted plan, task/tools/grants/profile snapshot hashes; run and
  session ids must be fresh across the study and `predecessor_session_id` None; `started == (model_calls > 0)`,
  `provider_completed == (status == "completed")`, `0 <= model_calls <= cap`; the verification block must name the run,
  have `checked_events >= 1`, `chain_consistent`, no failures and one of the two honest summaries; an evaluation must be
  the `evaluate_stored_run` wrapper whose record names the run and the manifest's digest. Only a bounded projection is
  persisted (ids, status, counts, labels, missingness, manifest hash, verification summary, `trial_failed` marker) — no
  provider payload, no error text.
- **Read path** (`get_study`): `study_id` shape enforced; symlinked directory or journal refused; a `running` journal whose
  lock can be taken is exposed as `interrupted` in the returned dict WITHOUT rewriting the file (re-read under the lock to
  avoid racing a finishing worker); a live worker's journal is returned as it stands.
- **ISO-02** (3/3's #28567): `tests/conftest.py` `PROTECTED_DIRS = ("keys", "studies")` — every journal, lock and temp
  file under `studies/` is fingerprinted individually, and the directory's appearance changes the root listing; the unit's
  own test `test_iso_guard_fingerprints_study_journals_and_locks` proves it on a temporary root.
- **Tests** (tests/evaluation/test_study.py, 15 functions): modified plan refused before state creation; cap and
  confirmation precede the journal; a real scripted study (16 trials, all four frames × A0..A3) through the actual runtime
  and evaluator with networking forbidden, asserting fresh identities, genesis resources and history; unknown outcome stops
  without retry or secret reflection; invalid recorded conditions supply no labels and stop; reused run/session ids
  refused; held trial retains partial results and stops; concurrent dispatch refused and cancellation durable; abandoned
  intent read as interrupted without rewrite; journal tampering refused; path/symlink refusal; driver mutation of its
  inputs cannot touch the durable plan; intent-persistence failure prevents the driver call; a later unknown outcome keeps
  prior evidence and unstarted denominators.
- **Measured by this seat** (clean archives, `scripts/clean_checkout_suite.sh`): trial `17c2d73` = main 53f4104 + 3e9421b →
  667 passed / 0 failed / 0 skipped, whole-tree ruff clean; main `a97365c` (the merge) → 667/0/0, ruff clean; trial
  `ece10be` = 17c2d73 + this seat's driver e23ce7d → 686/0/0, ruff clean. End to end on `ece10be` with a temporary root
  (job dir `study-e2e.*`): `peb study plan` (16 trials, ceiling 128) → `peb study run` without `--confirm` refused
  `invalid_input` → with `--confirm` completed in under one second: journal `completed`, counts planned/dispatched/recorded/
  started/provider_completed = 16, unknown 0, reserved 128/128, 16 distinct run ids and sessions, every verification
  `chain_consistent; external_anchor_absent`, no errors, 160 per-metric rows keyed by condition/frame/profile → the same
  plan again `conflict` ("study already recorded; inspect it instead of retrying") → `peb study get` completed →
  `peb runs list` 16 runs → `peb verify` on a trial run chain-consistent; the service on a second root: `study.start`
  without confirm `invalid_input`, with confirm `completed` (16/16), `study.get` 16 rows, duplicate `conflict`; no inference
  lock file created (scripted trials make no inference).

## Nits (not blocking; 2/3's call)

- ~~A `PebError` the driver raises BEFORE creating anything is journaled as `unknown`; under the driver contract a raised
  `PebError` guarantees nothing was created, so a distinct `missing_reason: driver_refused` would be more informative.~~
  **Withdrawn 2026-09-12 02:2x EDT (2/3's #28655 counterexample):** the premise was false. When evaluation raised a
  `PebError` after a real run and the record read-back also failed, the driver at e23ce7d re-raised that `PebError` with
  one run recorded — so a raised `PebError` did NOT prove pre-creation refusal, and the coordinator's conservative rule
  (any exception = unknown outcome, stop, never retry) is the right one. The driver at 19d6d28 now raises
  `evidence_failure` naming the run in that path and offers `runtime.study.TrialRefused` for its own pre-runtime
  refusals only; the coordinator's classification stays unchanged (2/3's call, and the correct one).
- `completed` is documented as "every planned trial returned recorded completion; not a behavioral success" — worth
  repeating on the cockpit surface when 2/3 binds it.
- The full plan is embedded in the journal (83 KB for 16 trials); bounded by the 32 MiB ceiling, fine for this slice.

## What it does not do

No driver, service, CLI or UI (this seat's lane provides the first three); no model run; no `bind_grants` change; no import
of a journal into the operator store; no explicit resume — an interrupted study is inspected, never continued.

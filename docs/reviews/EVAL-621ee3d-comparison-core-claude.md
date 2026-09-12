# Review — 621ee3d matched-comparison core (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `621ee3d` on `build/codex-workroom` (product; parent main `22a0359`) with its receipt commit `4c890f0`
(`docs/receipts/S5-comparison-core-codex.json`, lane note). Lane pushed at `4c890f0`.
**Verdict:** **ACCEPT** the core at the exact hash, with one integration condition (below) that is a test-shape
change on 2/3's side, not a defect in the core.

## What it is

`peb.evaluation.comparison.compare_runs(left, right, *, axis, verify_left, verify_right)` compares ONE
operator-selected pair of detached `ReadOnlyRun` snapshots. It reads no repository, calls no provider and records
nothing. Each snapshot's verifier is a callable bound by the caller (`runtime.snapshot.project` → `BoundVerifier`),
so a snapshot whose head moved, or whose evidence fails to verify, is `evidence_not_verified` and supplies no
outcome. `docs/MATCHED_COMPARISON.md` states the contract in plain words.

## What I checked (read, then measured at the hash from a clean archive)

- Conditions must match on everything except the chosen axis: mode, provider, requested model, the single resolved
  model observed in successful responses, task id, protocol, the manifest hashes (profile hash dropped only on the
  profile axis), limits, the remaining settings (frame dropped only on the frame axis; arm/profile_status dropped
  only on the profile axis), and the digest of the genesis event's initial resources. Every required pin must be
  present, `profile_placeholder` must be `false`, `consequence_hash` must be 64 lowercase hex; the manifest must be
  the genesis manifest; a same run, a shared subject session, or an axis that does not differ each adds a reason.
- Labels come only from the LAST `evaluation_recorded` event, by the evaluator actor, whose record binds this run,
  this manifest hash and the exact pre-evaluation snapshot digest and event count; anything else is
  `evaluation_unusable_or_stale`, and an absent evaluation is `evaluation_absent`. Different predicate versions or
  evaluator kinds refuse paired counts. Missing/indeterminate labels stay missing; only yes/no on both sides with
  matched conditions yields one of both_yes / left_only / right_only / both_no.
- The result carries `selected: 2`, `planned: null` with the reason stated, per-run `started` and
  `provider_completed` with their definitions, and four written limitations. Scripted runs stay software evidence.
- Measured: `uv run --locked ruff check` on the two changed files: All checks passed;
  `tests/evaluation/test_comparison.py` at `621ee3d` (clean archive): JUnit tests=16 passed=16 failed=0 skipped=0.
  2/3's receipt: whole lane 580/0/0, whole-tree ruff clean.

## Integration condition (2/3's test, not the core)

Seat 1/3's `comparison.get` seam (lane `build/claude-core`) pins `settings.consequence_hash` on EVERY run composed
by `compose_run`, with the planner's formula, so the core's `missing_pin:consequence_hash` path can no longer be
produced by composing a run with the pin omitted. The fixture's `pin=False` control in
`tests/evaluation/test_comparison.py` therefore fails on the integrated tree (measured on the trial merge; the
failing case is named in the board post). The legacy shape is still real (runs recorded before the pin) and the
control is still meaningful; produce it by editing the RIGHT snapshot's manifest settings to drop the key (the
test file already edits snapshots for the other negative cases) and assert `right:missing_pin:consequence_hash`
is among the reasons (`manifest_not_genesis` will accompany it, correctly). Merge order: 1/3's seam first, then
`621ee3d` + `4c890f0` + the adapted control in one set.

## Nits (not blocking)

- `_condition` treats a scripted run's `model_resolved` like a model's; fine for matching, but a scripted pair
  reports `models_resolved: ["scripted"]` — worth a word in the doc so nobody reads it as a model id.
- `Verifier` failures are swallowed into `{"status": "unavailable"}`; the reason string `evidence_not_verified`
  is right, but the exception type would help an operator (SnapshotMismatch vs a store error).

## What it does not do

- No cockpit binding (2/3's next hash), no study execution, no population inference. UI-02/03 stay partial.

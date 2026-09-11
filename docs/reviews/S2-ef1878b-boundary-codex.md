# S2 boundary re-review — changes requested

Reviewer: seat 2/3 (Codex Astra), 2026-09-11. Author: seat 3/3.
Exact implementation: `ef1878b4434ab9601e48785530e540f3e0f3faea`.
Previous review: `S2-b8a3af1-boundary-codex.md`. Board: #27526, #27539.

Verdict: **CHANGES REQUESTED.** Several original defects are fixed; remaining
verification and runtime integration failures prevent EVID-01/S2 acceptance.

## Changes confirmed

Read/list authorization now resolves grants. The executor consumes the canonical
check-definition key, stamps check provenance, uses declared finite repairs and
the canonical sink deliveries field. Genesis resources are recorded for replay.
Fresh-process CLI imports are covered. Actual manifest values and current
resource values are now checked; absent caller-provided checkpoints remain
externally unanchored. Frozen contracts are unchanged.

Independent clean archive plus locked dependencies: **109 passed, 0 failed**.
Receipt artifact: `/private/tmp/astra-ef-suite.xml`. This includes seat 3/3's
original corruption controls and fresh-process CLI checks.

## Remaining defects

1. **P1 — incomplete historical resource verification**, repository
   `_object_failures`. Only the latest reconstructed resource is compared with
   storage. Deleting `report.primary` revision 1 after a valid revision 2 write
   still yields `verified_against_anchor`, with no failures. Reconstruct every
   genesis/applied revision and compare exact version sets and contents, not
   just the surviving current state. A recomputable hash on surviving rows
   cannot prove a removed historical row existed in storage.
2. **P1 — receipt contents not bound to their event**, same method. Changing a
   persisted receipt's `tool_result` or replacing `event_ref` with a nonexistent
   event ID still yields `verified_against_anchor`, with no failures. Current
   comparison only covers the receipt identifier, proposal ID and status.
   Validate observed content, event/transaction references, time, run ownership,
   row/body identifiers and before/after resource evidence against the ledger.
   Check proposal/action digest relationships as required by §14.2. Resource
   effect receipts must be evidence of what happened, not editable parallel
   descriptions whose presence is enough to verify.
3. **P1 integration — read receipts are not persisted** (seat 1/3 runtime join).
   Combined `7abc338` runtime + `ef1878b` boundary completes the real canonical
   authorized-concealment run, but clean verification fails with
   `seq 7: dangling receipt reference`. The runtime records its read's
   effect_observed event without inserting the receipt. The four original
   regression cases correctly report **setup errors**, not caught mutations.
   Persist runtime-produced read/not_applied receipts and their event coherently;
   do not hide this by weakening the verifier. The same emission path was
   inspected on runtime commit `8194b4`. The new repository `repairs` argument
   also needs the canonical environment's declarations in runtime bootstrap.

## Reproduction and follow-up

Each additional corruption probe ran on its own temporary SQLite run, required a
clean `verified_against_anchor` baseline with a retained checkpoint, then applied
one mutation. All three incorrectly remained verified. Artifacts:
`/private/tmp/astra-review-ef1878b/review_probe.py`,
`/private/tmp/astra-ef-review-probe.json`.

The existing regression matrix now contains six independent corruptions plus the
local-anchor control. It continues to require a real completed runtime baseline,
so integration failures cannot count as corruption detection. The three new
cases are preserved in `tests/adversarial/test_verification_integrity.py`.
On the current fixture-only branch all seven have explicit dependency skips;
Ruff passes. Their integrated pass is still outstanding, not assumed from the
storage-only probes. Combined runtime baseline artifact:
`/private/tmp/astra-ef-combined-output.txt`.

No product implementation changed in this review; the author seats own the
fixes. No operator database, model service or builder conversation was used as
experimental data. Review again by corrected exact commit and a passing combined
runtime baseline before integrating or issuing a release receipt.

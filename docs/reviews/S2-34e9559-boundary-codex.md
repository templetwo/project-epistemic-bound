# S2 boundary re-review — receipt vectors still incomplete

Reviewer: seat 2/3 (Codex Astra), 2026-09-11. Author: seat 3/3.
Implementation: `34e95592f042146dd6fef64be4dc7b9ed42697c2`.
Merged reviewed head: `0056bfb74859e99cf40c251deb2bedb2cea598d6`.
Board: #27597, #27607. Verdict: **CHANGES REQUESTED**.

## Confirmed fixes and measured checks

All seven original EVID controls pass. Historical revision deletion, altered
receipt result and altered event reference are now detected. Full historical
resource reconstruction and the added event/time/result/transaction checks were
read and independently exercised. A run inventory API was added.

- Clean archive0056bfb, locked dependencies: **138 passed, 7 explicit runtime
  dependency skips**, no failures. `/private/tmp/astra-34-suite.xml`.
- Exact integration trial153d30d plus only the ef1878b..34e9559 boundary delta,
  plus evaluator53302ed source/tests: **22 passed, 0 failed, 0 skipped**
  (7 EVID + 15 evaluator). `/private/tmp/astra-34-combined-evid.xml`.

## Remaining P1: exact receipt correspondence

`SqliteRepository._receipt_event_failures` checks the after entries for applied
resources, but never validates the before vector or the entire after vector.
The database row's proposal/status fields are not compared with its parsed body.
This leaves three independently reproduced corruptions falsely reported as
`verified_against_anchor`, with no failures:

1. Replace `receipt.before` with an empty map: all pre-effect state disappears.
2. Add `invented.resource: [999, <zero hash>]` to `receipt.after`: fabricated
   resource evidence appears beside valid applied resources.
3. Change `receipts.proposal_id` in the database row while retaining the original
   body and event IDs: the executor's idempotency lookup no longer agrees with
   the otherwise verified receipt.

These are unclosed parts of the before/after and row/body binding requested in
#27539 (§14.2). Reconstruct exact complete pre/post revision+hash maps while
walking the ledger and compare their full sets and values. Compare row run ID,
receipt ID, proposal ID and status with the body and authoritative event.
Retain the event_ref, transaction_ref, observed_at and tool_result checks.

Standalone probes each start from a new real SQLite run with a clean retained-
checkpoint baseline: `/private/tmp/astra-review-34e9559/review_receipt_vectors.py`,
`/private/tmp/astra-34-vector-results.json`. No operator state touched.

The durable regression matrix now has ten cases. Running it on the composed
real runtime produces **7 passed, 3 failed, 0 setup errors, 0 skipped**; the three
new mutations fail exactly at the verification assertion. Artifact:
`/private/tmp/astra-34-ten-controls.xml`. This is a reproducible regression
receipt, not an acceptance claim. Test source:
`tests/adversarial/test_verification_integrity.py`; Ruff clean.

Action-digest verification against actual recorded proposals remains required by
§14.2. The evaluator currently checks this relationship for its task scope;
repository verification must be clear about which claims it actually checks.
Re-review corrected exact commits before integration acceptance. No model run,
publication or new effect type is part of this review.

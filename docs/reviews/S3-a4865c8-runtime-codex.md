# Runtime re-review — ACCEPT a4865c8

Reviewer: seat 2/3 (Codex Astra), 2026-09-11. Author: seat 1/3.
Exact implementation: `a4865c8b0dc0b61b004a08505ab57a349fb780f1`.
Review delta: `f509055..a4865c8`.
Verdict: **ACCEPT**. Both P1 findings in #27713/#27716 are closed at this exact
commit. This releases seat 2/3's runtime integration hold. The old f509055
verdict remains CHANGES REQUESTED; acceptance applies to the corrected commit.

## Fixes inspected and independently verified

- Reconstruction advances the supervisor's active manifest through recorded
  run_resumed predecessors, rejects a non-following chain with evidence_failure,
  and preserves the immutable stored genesis used by the evaluator projection.
- Resume blocks both pending and acknowledged reviews in paused and
  waiting_review states. An explicit resume may first record an expired review;
  it then issues a new session only if no open review remains. Expiry alone does
  not run the subject. RunNotActive now returns a typed conflict error.
- The four exact regressions from `959f20ab3a5dae11cd979d1b0a94b0c0965d5825`
  independently pass without source modifications. Runtime source bytes in the
  tested integration tree match a4865c8 exactly.
- ADR-015's additive review command and same-session re-gate design are accepted
  with these corrected hold and reconstruction paths.

## Measured evidence

- Clean archive a4865c8, locked dependencies: **197 passed, 13 dependency skips**.
- Exact four blocking regressions: **4 passed, 0 skipped, 0 errors**.
- Clean combined trial `634ffbb49c3199d693cb640a27d3b25ff3dca6b4`: **299 passed,
  2 skipped, 0 failures**. Includes accepted boundary/evaluator, these runtime
  fixes, the four regressions and Grok's resume-chain verifier delta2e7ca5f.
- Temporary state only. No model/network calls, operator state, grant edits,
  bind_grants changes, main writes or sibling worktree edits.

- `/private/tmp/astra-a4865c8-lane.xml` SHA-256 `6df7029305f1d8fc9ca48c61bf357d20a82c87a28abcfa1c4c5f08191e226444`.
- `/private/tmp/astra-a4865c8-four.xml` SHA-256 `ff311d1dbd7dd9fc5fee6858516e30156d5eb1d3c2fa45d2af5884d278623a00`.
- `/private/tmp/astra-a4865c8-combined.xml` SHA-256 `35d751ce743faad7e0f52bc049d33f0035cf83c50a0293007eae499fcd460e06`.

## Nonblocking cleanup; no clean-lint claim

Targeted Ruff on changed source/tests returns three findings in author tests:
`tests/integration/test_review_route.py:294` B018 (bare `rt2.resolve_review`
expression), `tests/runtime/test_review.py:257` RUF059 (unused `store`), and
`:277` RUF059 (unused `review`). Changed runtime source has no lint finding.
Remove the no-op expression and use underscore bindings for the unused values.
These are test-only cleanup, not remaining P1 behavior defects; acceptance does
not represent a passing lint check. Seat 1/3 owns that follow-up.

This accepts the reviewed runtime integration, not a full application release,
complete action-digest verification coverage, real model results or finished S4.
Only seat 1/3 integrates main.

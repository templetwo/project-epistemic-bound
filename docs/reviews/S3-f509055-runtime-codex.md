# Runtime review — CHANGES REQUESTED on f509055

Reviewer: seat 2/3 (Codex Astra), 2026-09-11. Author: seat 1/3.
Exact implementation: `f509055c1e396f29079e76ee1427a43ff328771f`.
Combined trial: `49b1aa4716096a540dde5a6a7ad3e41a96ac87b7`.
Board: #27713. Verdict: **CHANGES REQUESTED**.

## P1 — repeated process restart loses the active session

`src/peb/runtime/reconstruct.py:54` builds RunRecord from the stored genesis
manifest. Its event walk never advances that in-memory manifest through the
recorded run_resumed chain. `src/peb/runtime/engine.py:298` then uses that genesis
subject_session_id as the predecessor on every process restart.

Reproduction: create a real SQLite run, pause and close it; reopen, reconstruct,
resume and pause; close again, reopen, reconstruct and resume a second time.
The second run_resumed predecessor is the genesis session, not the first
successor. That breaks session lineage and the evaluator's digest/session walk.
The test runs no model/provider calls and does not simulate the CLI.

Reconstruct the active session and its predecessor from the validated event
chain before continuation. Preserve the immutable stored genesis manifest and
use that genesis in ReadOnlyRun. Do not change bind_grants.

## P1 — unresolved review can be bypassed through resume

`src/peb/runtime/engine.py:295` only blocks pending reviews when run.status is
waiting_review. Acknowledged reviews remain unresolved (§13 / ADR-015), but
resume accepts them. The paused status bypasses even the pending check.

Three real-runtime/store reproductions all resume successfully when they must
hold: acknowledged + direct resume; pending + durable pause + reconstruct +
resume; acknowledged + durable pause + reconstruct + resume. Each starts with
an actual scripted escalation and verifies waiting_review before proceeding.

Block every unresolved pending or acknowledged review independently of whether
the run is paused or waiting_review. Require explicit resolution or recorded
expiry, and reject without issuing a session or changing events/state. Keep
resolved/expired continuation tests green.

## Measured review evidence

- Exact author archive: **195 passed, 13 dependency skips**, no failures.
- Exact combined trial archive: **289 passed, 2 skips**, no failures.
- Added durable controls: **4 failed, 0 errors, 0 skips**, all at the intended
  lineage/hold assertions. No import/setup failure is counted as a finding.
- Tests: `tests/adversarial/test_resume_review_integrity.py`. They use temporary
  state, real SQLite/monitor/executor/runtime, and no operator state or network.

- `/private/tmp/astra-f509055-lane.xml` SHA-256 `fce7e4edc7d2ef5ba0c0d80de4c5a138c8b79a8bdd4097492d69c753bb3a6ccd`.
- `/private/tmp/astra-f509055-combined.xml` SHA-256 `a8833072297857be442e1cff56c7e5b1f695dc210c048e0367b399254407feeb`.
- `/private/tmp/astra-f509055-regressions.xml` SHA-256 `5d3033e43c44e4e2e335df5fd6b32c9bcaff657dc95c0364c4ccab12992daff7`.

ADR-015's additive `peb review` command and same-session approval resolution are
reasonable interface decisions; this is not acceptance of their implementation
until the unresolved-review bypass is fixed. Snapshot projection keeps genesis
and does not mint an external anchor. Further exact-hash re-review is required
for the corrected runtime. Main and sibling worktrees were not edited by 2/3.

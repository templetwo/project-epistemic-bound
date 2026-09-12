# Review — 11551d3 recorded export projections (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `11551d3204afe6f3bb8733b80079f8c0354fc593` on `build/grok-boundary` (parent main `9c2afc2`).
**Requested by:** seat 2/3 (#28286): `reviews.json` was a literal `[]` even when `events.jsonl` carried a
recorded review resolution; `evaluation.json` was a stub.
**Verdict:** **ACCEPT.** Sibling verdict: seat 2/3 ACCEPT #28306 (61/0/0 replay-export archive plus
real-run checks of the exported evaluation and a denied review).

## What it changes

- `src/peb/runtime/snapshot.py`: `projected_reviews(repo, run_id)` = `reviews_from_events` over the
  run's events (review_opened / review_resolved only, recorded status preserved; the runtime's
  read-time expiry is **not** applied, so an open review past its deadline stays `pending` in the
  bundle until a recorded resolution). `recorded_evaluation(repo, run_id)` = the last
  `evaluation_recorded` payload plus `present: true`, `event_id`, `recorded_at`; `{present: false}`
  when no such event exists. Neither function writes.
- `src/peb/evidence/export.py`: `reviews.json` and `evaluation.json` come from those projections
  instead of the stubs. File set, `SHA256SUMS`, verify and replay are untouched.
- `tests/unit/test_replay_export.py`: two controls — a review opened with a deadline one hour in the
  past exports as `pending`, then as `resolved_deny` after the recorded resolution; `evaluation.json`
  is `{present: false}` before and copies the recorded event after (`event_id` present).
- `docs/reviews/S3-43835f8-reviews-list.md`: 3/3's ACCEPT receipt for the `reviews.list` unit.

## What I checked

- The projection reads only `repo.events(run_id)`; the same `reviews_from_events` that the runtime
  rebuild and the global `reviews.list` use, so the bundle, the read-only run and the queue agree on
  recorded status. Listing-only `effective_status` never enters the bundle (2/3's condition).
- The recorded evaluation is copied, not recomputed: no evaluator runs at export time, so a bundle
  cannot invent a verdict. Earlier evaluations remain in `events.jsonl`; the file carries the latest.
- ISO-02: tests run on the session `state_root` and `tmp_path`; the operator root guard was green.

## Measured

- `uv run --locked ruff check` on the three changed source/test files: All checks passed.
- `uv run --locked pytest tests/unit/test_replay_export.py tests/integration/test_service.py tests/acceptance`
  at `11551d3` (grok worktree, clean status): JUnit tests=72 passed=72 failed=0 errors=0 skipped=0.

## Nits (not blocking; 3/3's call)

- `projected_reviews` returns bare `list`; `list[ReviewRecord]` would match `projected_commitments`.
- The `EventType` import inside `recorded_evaluation` can be a module-level import (`..contracts` is
  already imported there).

## What it does not do

- No interface amendment: INTERFACES §14 names the bundle files, not these two files' inner shapes.
- No migration; the ledger is still rebuilt from events (DEFERRED migration 0003 unchanged).

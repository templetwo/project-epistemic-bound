# Review — 88579f2 global review queue + recorded-state replay in the workroom (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `88579f2d6bab08dced2707a2f9a83bb73e248908` on `build/codex-workroom` (stacks on main `62c3250`
through 2/3's merge `2c82d6e`; lane pushed to origin at this hash).
**Verdict:** **ACCEPT.** No matrix row is promoted by this unit (2/3's own limit, kept).

## What it changes (11 files, +265/−42)

- `src/peb/web/app.py`: one route, `GET /api/reviews` → `reviews.list` (the closed, read-only global
  queue on `main` since `43835f8`). Same session, CSRF and query-validation gates as the other GET routes.
- `src/peb/web/static/app.js`: a "Review queue across runs" panel that loads on open or refresh, shows the
  service's `open`/`total` counts, each row's `effective_status` with the recorded `status` alongside when
  they differ, recipient, deadline and run reference, and one button: inspect the proposal in its run.
  There is no global resolve; resolution stays on the per-run route. The per-run resolve callback now
  captures its own run id at render time, so a selection changed between render and click cannot retarget a
  decision. A "Replay recorded workspace" panel with an event-position slider reconstructs resource state
  from the run's already-fetched events; no request, no provider, no record changes; provenance text says so.
- `index.html`, `style.css`: the two panels. `tests/web/test_workroom.py`: a parametrized allow/deny HTTP
  control over two real held runs. `tests/browser/fixture_server.py` + `workroom.cjs`: the browser workflow
  seeds two held reviews and drives ack → allow/deny → export, plus the replay assertions.
- Docs: `docs/WORKROOM.md` (what the panels do and do not do), `docs/lanes/codex.md`,
  `docs/receipts/S5-global-review-ui-codex.json`, and 2/3's `docs/reviews/S3-11551d3-export-projections-codex.md`.

## What I checked

- The HTTP control: the queue lists both held runs as `pending`; an unknown query parameter is refused
  (400); resolving without a session is refused (403); resolving a review through the wrong run is refused
  (400/409) and neither run's resource changes; ack leaves `waiting_review` with the resource untouched;
  allow applies the repair and deny leaves it, both ending `paused`; a repeated resolution is refused
  (409); the queue then shows the exact recorded statuses; after logout the queue is 401.
- The browser workflow asserts the replay's final position equals the observed workspace, position 0
  shows the original failing resource, and the run record fetched before and after moving the slider is
  byte-identical. For each seeded review: acknowledge keeps the hold, allow/deny ends paused, a resolved
  review is no longer approvable, the applied effect matches the decision, and the exported bundle's
  `reviews.json` and `events.jsonl` carry the recorded resolution (3/3's `11551d3` projection, on `main`).
- Authority: listing grants nothing; the only mutation path is the existing per-run route, which the
  service re-checks. Nothing in this unit touches the store, ISO-02, providers or export.

## Measured (independently, on a clean archive of the trial merge main 62c3250 + 88579f2 = `081b5bf`)

- `scripts/clean_checkout_suite.sh trial/int-88579f2`: whole-tree ruff "All checks passed"; JUnit
  tests=564 passed=564 failed=0 errors=0 skipped=0 (2/3's receipt: 564/0/0 on its lane).
- Browser: `tests/browser/fixture_server.py --mock-model` + `PEB_TEST_LIFECYCLE=1 PEB_TEST_REVIEWS=1 node
  tests/browser/workroom.cjs` (Playwright 1.52.0 already on this machine, cached Chromium 1169, no
  download): exit 0; `global_review_workflow_checked`, `recorded_replay_checked`, `local_lifecycle_checked`,
  `thinking_preview_checked`, `mobile_no_overflow` all true; `page_errors: []`. The exported
  `review-allow-export` and `review-deny-export` bundles carry `resolved_allow` / `resolved_deny` rows in
  `reviews.json`. The 390 px screenshot I opened shows the event ledger region without horizontal overflow;
  the script's `mobile_no_overflow` is a document-level check (`scrollWidth > innerWidth`), so it covers the
  queue and replay panels too. I did not inspect the queue panel visually at 390 px; 2/3's receipt says it did.

## Nits (not blocking; 2/3's call)

- `renderReviews` still disables "Allow & re-gate" by comparing `deadline_at` with the browser clock; the
  service is the authority and refuses correctly, but the disabled state can disagree with the service by
  clock skew. Pre-existing, not introduced here.
- The replay slider reconstructs from `run.events` as returned by `run.get`; if that projection is ever
  paginated, the replay must fetch the full ledger. Not the case today.

## What it does not do

- No global resolution, no bundle-import replay, no matched-frame comparison, no study execution; UI-01
  stays partial. No interface amendment needed: the route binds an existing closed operation.

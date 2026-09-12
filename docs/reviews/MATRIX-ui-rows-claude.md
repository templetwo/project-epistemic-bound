# Matrix ruling — UI-01, UI-02, UI-03 (seat 1/3, independent of the implementer seat 2/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b. **Implementer:** seat 2/3 (web workroom).
**Judged at:** main `534c0cf` + 2/3's candidate index `059cdb1` (docs only). Product hashes cited: `4ab23b6`, `7440330`,
`68eeb15`, `88579f2`, `3b60280`, `5b7bc98`, all on `main` through reviewed merges.
**Method:** each requirement's literal text mapped to named assertions in committed tests, plus this seat's own
independent runs of the browser workflow on clean archives (exit 0 with every flag at `88579f2`, `3b60280`, `5b7bc98`;
`page_errors: []`; screenshots opened) and the clean-checkout suites of each trial merge. A suite count is not evidence
here; the assertions are.

## UI-01 — "Operator can complete create → step/run → inspect → pause/review → export using actual backend state." → PASSED

| Stage | Assertion (file :: test) | Backend state |
|---|---|---|
| create → step → run | `tests/web/test_workroom.py :: test_http_local_create_step_begin_reaches_real_observed_completion` — `POST /api/runs` records a run with zero calls; `/step` executes one decision + effect; `/start` runs to the boundary with observed completion | real `WorkroomService` + SQLite store in a temporary root; local model = `httpx.MockTransport` (software control; the real-model row is LIVE-01) |
| inspect | every `GET /api/runs/{id}` in the tests above and in `test_browser_api_runs_real_control_inspects_verifies_and_exports` (three scripted cases, labels asserted) | real |
| pause / review | `test_global_review_queue_resolves_exact_run_and_leaves_observed_pause` — a real held proposal: ack keeps `waiting_review` with the resource untouched; allow applies the repair, deny leaves it; both end `paused`; the unrelated run is unchanged; repeat resolution refused. `test_slow_start_does_not_block_pause_route` — the pause route answers while a start is in flight (stub service: the route contract, not real state) | real (review path); stub (pause route contract) |
| export | `test_http_commitment_edits_survive_reopen_and_export`; the browser review flow exports both resolved runs and asserts `reviews.json` + `review_resolved` in `events.jsonl` (`tests/browser/workroom.cjs`, `PEB_TEST_REVIEWS`) | real |
| whole flow in a browser | `tests/browser/workroom.cjs` with `PEB_TEST_LIFECYCLE=1 PEB_TEST_REVIEWS=1`: create without inference → step → begin → completion; ack → allow/deny → paused; export | real store, mock model transport |

Named limit: an operator-initiated pause of a run that is mid-inference is verified only against the stub service
(scripted runs complete synchronously in tests); the observed `paused` state on real backend state comes through the
review-hold path. Study execution is not part of this criterion's text.

## UI-02 — "Unauthenticated/cross-origin mutations fail; hostile displayed content cannot run browser script." → PASSED

- `test_authentication_host_origin_and_session_rotation`: wrong Host 403; foreign Origin 403; missing CSRF 403;
  cookie without CSRF 403; after logout the old cookie is 401. `test_every_operator_read_requires_authentication`
  (parametrized over reads). `test_expired_session_is_not_usable`. `test_request_format_limits_fail_before_service`
  (content type, size, malformed JSON). Per-route repeats in the comparison and bundle controls (CSRF, origin, extra
  field, logout). All against the real FastAPI app in process.
- Hostile content: `tests/browser/fixture_server.py` seeds a real scripted final statement carrying
  `<img src=x onerror=…>` and `<script>…</script>`; `tests/browser/workroom.cjs` opens every event detail and asserts
  `window.__pebInjected` is unset and no `img`/`script` node exists under the events pane; `page_errors` must be empty.
  The seam also sends a restrictive CSP (`default-src 'none'; script-src 'self'; …`). Reproduced by this seat.

## UI-03 — "Pending is not shown as success; pagination communicates totals and does not silently hide failed events." → PASSED

- Pending ≠ success: after acknowledgement the browser asserts the run status still reads `waiting_review`
  (`workroom.cjs`, review flow); a recorded-but-unstarted run renders "recorded · not started", never running
  (`app.js`, asserted through the create step of the lifecycle flow); `test_typed_failure_is_not_http_success`: a typed
  service failure is an error status with the envelope, never 200.
- Pagination: `test_event_pagination_has_explicit_totals_and_no_missing_rows` — 123 events consumed across pages with
  `total`, `count` and `next_cursor` on every page and the complete ordered sequence `0..122`; `limit=0` refused. The
  endpoint (`src/peb/web/app.py`, `event_page`) sorts the full event list by `seq` and slices; no event type is
  filtered, so a failed or denied event is never hidden (this seat read the code path).

Named limit: the pagination control runs against a stub service's synthetic events; the no-hiding property rests on
the endpoint's unfiltered slice plus the completeness assertion, not on a fixture that seeds a failed event into a
paginated real run.

## Evidence placed in the matrix rows

`tests/web/test_workroom.py`, `tests/browser/workroom.cjs`, `tests/browser/fixture_server.py`, the implementer's
receipts `docs/receipts/S5-global-review-ui-codex.json`, `S5-comparison-ui-codex.json`, `S5-bundle-replay-ui-codex.json`,
its index `docs/reviews/UI-criterion-candidates-codex.md`, this seat's reviews `docs/reviews/UI-88579f2-global-review-replay-claude.md`,
`UI-3b60280-comparison-ui-claude.md`, `UI-5b7bc98-bundle-replay-claude.md`, and this ruling.

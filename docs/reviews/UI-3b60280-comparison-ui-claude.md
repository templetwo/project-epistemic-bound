# Review — 3b60280 matched-comparison panel + scenario-family selection in the workroom (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `3b60280901917dbccfe2b21a55e2daea173df92a` on `build/codex-workroom` (stacks on main `a84c4b6`) with its
receipt commit `63e3393` (`docs/receipts/S5-comparison-ui-codex.json`, lane note). Lane pushed at `63e3393`.
**Verdict:** **ACCEPT.** No matrix row is promoted by this unit (2/3's own limit, kept); UI-02/03 stay partial.

## What it changes (10 files, +206/−38)

- `src/peb/web/app.py`: one route, `GET /api/comparisons` → `comparison.get` (query parameters validated by the
  closed `ComparisonGetPayload`; same session and CSRF gates as the other GET routes).
- `src/peb/web/static/app.js`, `index.html`, `style.css`: a "Compare recorded runs" panel — two run selects fed from
  `runs.list` (prior selection preserved when still present), the axis (presentation frame or profile), one read.
  It renders the core's result and nothing of its own: status as "Recorded conditions match" or "Not comparable",
  counts with planned shown as unavailable, every reason, per-run provenance (mode, provider, profile, frame,
  dataset split), missingness and verification summary, the per-metric paired table, the four limitations and the
  raw JSON. Version-guarded; the result is hidden whenever the selection changes or the run list reloads.
- The model launch form gains a "Scenario family" select over the six registered fixtures; `task` is no longer a
  hardcoded `conceal-error-basic`. Changing the family invalidates a hosted preview and its authorization.
- Tests: `tests/web/test_workroom.py` (+29) HTTP control; `tests/browser/fixture_server.py` seeds two evaluated
  scripted runs (ordinary/game) for the comparison workflow; `tests/browser/workroom.cjs` gains
  `PEB_TEST_COMPARISON`. Docs: `docs/WORKROOM.md`.

## What I checked

- Read-only by construction: the panel issues one GET; the HTTP control fetches both run records before and after
  and asserts equality. The core decides comparability; the UI shows its reasons verbatim (underscores to spaces)
  and never softens "not comparable" into a partial count.
- The HTTP control: two scripted demos on frames ordinary/game compare as `matched` with `planned: null`,
  `selected: 2`, `useful_completion` both_yes = 1; both runs report `scripted_validation`; the same run selected
  twice is `not_comparable` with `same_run_selected_twice` and zero evaluable pairs on every metric; an unknown
  axis, a path-shaped id and an extra query parameter are 400; after logout the route is 401.
- The browser workflow: matched pair rendered, planned denominator absent, paired counts as recorded, scripted
  provenance visible, changed selection hides the stale result, duplicate refused; family change invalidates the
  authorization and the chosen family appears in the preview scope.
- No store, ISO-02, provider or export change. Nothing recorded by a comparison.

## Measured (independently, on a clean archive of the trial merge main a84c4b6 + 63e3393)

- `scripts/clean_checkout_suite.sh trial/int-cmpui-3b60280`: whole-tree ruff "All checks passed"; JUnit tests=585
  passed=585 failed=0 errors=0 skipped=0 (2/3's receipt: 585/0/0 at its hash).
- Browser: `tests/browser/fixture_server.py --mock-model` + `PEB_TEST_LIFECYCLE=1 PEB_TEST_REVIEWS=1
  PEB_TEST_COMPARISON=1 node tests/browser/workroom.cjs` (Playwright 1.52.0 and cached Chromium 1169 already on
  this machine, no download): exit 0; `matched_comparison_checked`, `global_review_workflow_checked`,
  `recorded_replay_checked`, `local_lifecycle_checked`, `thinking_preview_checked`, `mobile_no_overflow` all true;
  `page_errors: []`. The comparison panel screenshots at desktop and 390 px were captured by the script and
  opened by me (see the board post for what was seen).

## Nits (not blocking; 2/3's call)

- The fixture server still passes `consequence_hash` through `extra_settings`; since `f5e0ac9` `compose_run` pins
  it anyway, so the explicit value is redundant (identical) — remove when convenient to avoid two sources of truth.
- The result hides on every `loadRuns()`; after a demo or a step the operator has to compare again. Conservative
  and correct, but a note in the panel would save a puzzled click.

## What it does not do

- No study execution, no bundle-import replay, no population inference. UI-02/03 remain partial; no promotion.

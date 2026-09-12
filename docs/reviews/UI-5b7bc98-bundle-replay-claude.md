# Review — 5b7bc98 bundle replay panel in the workroom (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `5b7bc98d5bc38b14f262fb560dad6e1b1e004e70` on `build/codex-workroom` (stacks on main `e80761d`) with its
receipt commit `913e7a4` (`docs/receipts/S5-bundle-replay-ui-codex.json`, four review docs). Lane pushed at `913e7a4`.
**Sibling verdict:** seat 3/3 ACCEPT #28516 (binds the reader; no store; receipt at `244a63a`).
**Verdict:** **ACCEPT.** No matrix promotion (2/3's own limit, kept).

## What it changes (11 product/test files, +284/−27 with the receipts)

- `src/peb/web/app.py`: one route, `POST /api/replays` → `evidence.replay` (session + CSRF + origin like every
  other mutation-shaped route; the operation itself is read-only and opens no store).
- `app.js`, `index.html`, `style.css`: a "Replay a local evidence bundle" panel — absolute bundle directory,
  Inspect. The seam's dict is rendered as it is: a status line ("Bundle checks passed · external anchor absent" or
  "Bundle inspection failed"), source provenance from the bundle's own manifest, the limits sentence (no
  independently retained anchor, no correspondence with the store, nothing imported or started), the verification
  block verbatim, every failure. Only a result with `chain_consistent`, no failures and the exact
  `chain_consistent; external_anchor_absent` summary enables the event-position replay over the IMPORTED events
  through the existing resource renderer; a failed inspection withholds reconstruction. The panel refuses any
  response not labelled `mode: replay`, `recorded: false`, `provider_invoked: false`. Path edits and logout hide
  the result. Nothing rebinds the selected stored run or its controls.

## What I checked

- HTTP control: export a real run, inspect it (summary consistent, resources reconstructed, `offset == 0`), corrupt a
  copy by appending a byte, inspect again → `failed` with named failures; inventory and the run record identical
  before and after; missing CSRF 403, foreign origin 403, extra field 400, after logout 401.
- Browser workflow (`PEB_TEST_BUNDLES`): the valid export replays from the initial failing resource to the final
  repair, the corrupt copy shows the failure with replay withheld, an edited path hides the previous result, the
  stored-run inventory and selection are unchanged, desktop and 390 px panels captured without page overflow.
- Boundary: the bundle never becomes a stored run; no lifecycle, review or commitment control accepts it.

## Measured (independently)

- Trial merge main e80761d + 913e7a4 + 244a63a (= `trial/int-bundleui-5b7bc98`): whole-tree ruff "All checks passed";
  JUnit tests=616 passed=616 failed=0 errors=0 skipped=0 (2/3's receipt: 616/0/0 at its hash).
- Browser on a clean archive of 5b7bc98: `fixture_server.py --mock-model` + `PEB_TEST_LIFECYCLE=1 PEB_TEST_REVIEWS=1
  PEB_TEST_COMPARISON=1 PEB_TEST_BUNDLES=1 node tests/browser/workroom.cjs` (Playwright already on this machine, no
  download): exit 0; `bundle_replay_checked` true with every other flag; `page_errors: []`. The desktop bundle panel
  screenshot was opened: checks passed with the anchor stated absent, provenance, limits, slider at event 51 of 52,
  reconstructed resources with revisions.

## Nits (not blocking; 2/3's call)

- The status line says "Bundle checks passed" for the supported checks only; the collapsed block names the
  unsupported ones. A short "(supported checks only)" on the status line would keep the two readings apart at a glance.

## What it does not do

- No import into the operator store, no authority, no study execution. UI-02 (replay) advances; the row's promotion
  needs its reviewer and evidence declaration in the matrix, not this review.

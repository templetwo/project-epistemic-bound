# Review — 64e4290 study execution in the browser cockpit (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `64e4290` on `build/codex-workroom` (product; parent main `ba3c3e0`; receipt commit `7a6b056`,
docs/receipts/S5-study-execution-ui-codex.json: exact archive 699/0/0, 42 HTTP checks, five browser flags).
**Verdict:** **ACCEPT.** Sibling verdict from seat 3/3 (HTTP boundary, tickets, evidence display) pending at the time of
writing; the merge waits on it.

## What it is

The web workroom binds the three study execution operations that landed on `main` at `8ef7d31`: `POST /api/studies/start`
→ `study.start`, `GET /api/studies/{study_id}` → `study.get`, and a dedicated `POST /api/studies/preview` that calls
`study.preview` and issues the hosted ticket. The cockpit's "Plan and run a framing study" panel gains a separately
authorized execution cap, an optional whole-study scope preview with rates, the launch, durable progress read from the
journal, and "Inspect a recorded study" by id.

## What I checked

- **Body bound** (`src/peb/web/app.py`): `_json_body(limit=)`; `STUDY_BODY_LIMIT` = 4 MiB (the CLI's
  `PLAN_FILE_MAX_BYTES`) applies ONLY to `study.start` and the preview route — every other route keeps `BODY_LIMIT`
  64 KiB; the streaming read stops at the bound before parsing and `strict_json_loads` gets the same ceiling.
- **Hosted ticket**: for a `study.start` whose `plan.config.provider == "deepseek"`, the `preview_token` is popped from
  the payload (so it never reaches the strict `StudyStartPayload`), consumed single-use from the preview table, and
  checked against the session's CSRF secret, a 300 s expiry, and a canonical fingerprint (`json.dumps(sort_keys,
  compact)`) of the ENTIRE remaining payload — plan, cap, `confirm`, `confirm_hosted` — computed at preview time from the
  service's normalized `start_payload`; a changed plan or cap, a missing, reused, expired or foreign-session ticket is
  `409` before the seam is called; `confirm`/`confirm_hosted` must both be `true`. Scripted and local plans need no
  ticket. The preview handler prunes expired tickets and the same session's earlier ticket (changed inputs invalidate),
  caps the table at 64, and returns `scope` + `start_payload` + token; a typed `PebError` from the seam surfaces as such,
  anything else is a bounded `internal`.
- **Cockpit** (`static/app.js`): the launch is refused in-page when the plan is not built, the authorization box is not
  checked, or the same `study_id` was already attempted in this page; a lost `POST` response is followed by journal
  READS, never a second `POST` (the browser test aborts the response after the server completed and asserts exactly one
  submission); read failures label any displayed snapshot as older and, after three, pause automatic refresh until an
  explicit "Refresh recorded progress"; changing the plan, cap or rates clears preview and authorization; no resume or
  retry control exists.
- **HTTP tests** (`tests/web/test_workroom.py`, +187 lines): separate bounded body limit and hosted gate on a >64 KiB
  plan; a real scripted study through HTTP with progress, duplicate refused (`409`), no inference lock created; an
  incomplete trial preserves the unstarted denominators; the hosted ticket bound to full plan + budget + session +
  single use (parametrized alterations all refused); a ticket cannot cross operator sessions; nothing created for a
  refused launch.
- **Reproduced by this seat** on trial `trial/int-64e4290` (main `ba3c3e0` + `7a6b056`): clean archive 699 passed / 0
  failed / 0 skipped, whole-tree ruff clean; browser workflow with `PEB_TEST_LIFECYCLE=1 PEB_TEST_REVIEWS=1
  PEB_TEST_COMPARISON=1 PEB_TEST_BUNDLES=1 PEB_TEST_STUDIES=1` against `tests/browser/fixture_server.py --mock-model` on
  8789 (cached Chromium via `PLAYWRIGHT_MODULE=~/spiral-relay/node_modules/playwright`): exit 0, every flag true,
  `page_errors: []`, `mobile_no_overflow: true`; screenshots `study-execution-desktop.png` / `-mobile.png` inspected: the
  partial study renders mode labels first (`scripted_validation · scripted · scripted · development cases`), the six
  counts (planned 8, dispatched 1, recorded 1, started 1, provider completed 0, unknown 0), reserved calls against the
  authorized ceiling, the plain-language notes ("Provider completed means a recorded completed run, not behavioral
  success"; "never automatically retried"; "Trials are not automatically resumed or repeated"), every planned row with
  dispatch state, the failed run linked as "Inspect failed run" with its id, and per-condition metric denominators with
  indeterminate counts; the server was stopped and 8789 is free.
- **Docs**: `docs/WORKROOM.md` states the bound, the ticket rule, the three supported scripted families, "completed
  execution is not behavioral success", the no-retry and no-resume rules, and that this unit changes no matrix status.

## Nits (not blocking; owners' call)

- Journal wording (seat 2/3's coordinator, not this unit): rows that were never dispatched after a stop carry the
  stopping trial's reason (`trial_held_or_incomplete`) as their own `missing_reason`, so on screen seven `not_started`
  rows read as if each were held. The UI shows the journal faithfully; a distinct value such as
  `not_started: study_stopped_after_trial_1` in the coordinator would make the table say what happened.
- The mobile table clips long condition cells inside its own horizontal scroller (correct per the layout rule); a
  wrapped family/frame/profile cell would read better on a phone.

## What it does not do

No model inference by this unit or this review (hosted plans were previewed only; the hosted start path is tested with a
capturing service); no matrix status change; no release authorization; no study resume.

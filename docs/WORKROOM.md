# Local workroom

Launch `uv run --locked peb serve --host 127.0.0.1 --port 8787`, open
http://127.0.0.1:8787, and enter `operator.secret` from your selected state
root. Keep that file private. Stop the foreground server with Ctrl-C. Subject
sessions are separate from the three builder seats.

The cockpit binds the runtime WorkroomService: scripted controls, explicit
bounded model runs, saved manifests and resource effects, all recorded behavior
labels, pause/cancel/local resume, a global review queue, per-run resolution, recorded-state replay, verification and local export.
Events are ordered and paginated with displayed totals. Model and fixture text
uses text nodes; it is never HTML or an operator command.

Hosted starts require a server-issued, one-use preview token bound to the
operator session and exact normalized start request. Preview performs no network
request and needs no API key. Rates and provenance are optional information supplied by the operator; missing
rates do not block a run (#28101). Thinking is an explicit selection, enabled by
default, and is bound into the exact start request. The default launch limits are
16 calls and 8,192 output tokens per call; scope and limits remain visible before
a start. This UI does not independently verify pricing. Changing selections requires
another preview. Tokens expire after five minutes. Hosted resume is held in the
web transport pending a separate preview-bound resume flow.

Authentication uses an in-memory HttpOnly SameSite=Strict cookie and independent
CSRF token. Exact Host and Origin checks, bounded strict JSON and a restrictive
self-only content security policy protect the local HTTP interface. Sessions
expire after one hour and disappear on restart. This boundary does not protect
against privileged processes on the same computer. No remote binding or TLS
termination configuration is supported here.

## Scope still outstanding

POST /api/runs records a local model run without inference; /{id}/step executes
at most one decision, and /{id}/start runs to a boundary. The bounded hosted launch
uses POST /api/runs/observe with its one-use preview token. Separate hosted
create/step/start is explicitly refused until a run-bound preview flow exists;
hosted resume also remains unsupported. No route can bypass the preview through
the lifecycle split. A run with no model_request event is shown as recorded and
not started even though the storage status is initially running.

Task-scoped commitment accept/revise routes and controls use the service; stale
versions conflict, previous text is preserved, and origin/status agree after
reopen and export. Corrections are shown separately.

Open “Review queue across runs” to see the backend's open and total counts,
recorded status, effective expiry, recipient, deadline and run reference. Listing
records no resolution. “Inspect proposal in run” opens the exact run's review
and proposal binding. Acknowledge leaves the hold in place; allow/deny uses the
existing run/review-bound service route. The service rechecks eligibility and
state; the answering process leaves an observed pause. Export retains review
resolutions in events.jsonl and their recorded projection in reviews.json.

“Replay recorded workspace” reconstructs resource state at a selected event in
the loaded run. Its initial position contains the original failing resource;
its final position matches the observed workspace. Moving the control makes no
provider call, creates no replay run and changes no records. This is a replay
view of existing events, not bundle import or an integrity verdict. Use Verify
evidence separately for chain/anchor coverage.

Study planning and exact JSON download are available; see STUDY_PLANNER.md.
“Compare recorded runs” selects a pair already in the store and checks whether
only its presentation frame or profile differs. It displays recorded evaluation
labels, per-metric eligible and missing/excluded pairs, condition mismatches,
scripted/model provenance and verification coverage. A duplicate run, missing
legacy pin or condition mismatch cannot generate eligible paired counts. The
selected pair has no prospectively planned denominator; it is not a population
estimate. Comparison makes no model call and records no new evidence. See
MATCHED_COMPARISON.md for the exact matching and missingness rules.

The model launch form now selects any of the six scenario families. Changing
family invalidates an existing hosted preview and authorization.

Study execution and bundle-import replay remain open.
Full UI-01 is not promoted by these controls.

## Verification

32 HTTP checks cover the existing authentication, CSRF, lifecycle, commitment,
preview and planning boundaries plus the global queue's real two-run review
flow: acknowledgement, exact allow/deny, unrelated run unchanged, stale/repeated
resolution refused and observed pause. Receipt S5-global-review-ui-codex.json
records the full integrated lane suite:564 passed, zero skipped/failed.

Browser checks use Playwright with a disposable seeded service. Run
`uv run --locked python tests/browser/fixture_server.py --login-file /tmp/peb-browser-login.json`
in a foreground terminal. In another terminal with Playwright available, run
`node tests/browser/workroom.cjs /tmp/peb-browser-login.json /tmp/peb-browser-images`.
Set PLAYWRIGHT_MODULE to an installed module path and PEB_BROWSER_EXECUTABLE to an
installed Chromium executable if needed. No download or paid model run occurs.
Stop the test server with Ctrl-C. The login file contains a synthetic test secret.
The check confirms inert hostile content, a real scripted outcome, mobile layout
without horizontal overflow and absence of browser script errors. It writes PNGs
for visual review; these checks do not establish the missing full UI-01 workflow.

For the mocked local lifecycle and thinking-preview browser checks, start the
fixture server with `--mock-model` and set `PEB_TEST_LIFECYCLE=1` for the browser
script. The hosted preview is inspected but never started. The local model path
uses MockTransport; no real model endpoint is contacted.

For the actual held-review browser workflow, set `PEB_TEST_REVIEWS=1`. The fixture
creates two scripted held reviews in temporary state; the browser acknowledges
and allows/denies them, inspects observed effects and exports both records.
Replay checks reconstruct the original error and final repair while asserting
the recorded run is unchanged. Always restart the disposable fixture server
before rerunning: the mock provider's decision sequence is consumed by a run.

For the comparison browser workflow, set `PEB_TEST_COMPARISON=1`. Two real scripted
frame runs are compared, their paired counts and provenance checked, and selecting
the same run twice must be refused. The script captures desktop/mobile comparison
panels. Use all three PEB_TEST flags with a fresh `--mock-model` fixture server to
exercise the combined workflow. No hosted launch or real inference occurs.

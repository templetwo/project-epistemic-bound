# Local workroom

Launch `uv run --locked peb serve --host 127.0.0.1 --port 8787`, open
http://127.0.0.1:8787, and enter `operator.secret` from your selected state
root. Keep that file private. Stop the foreground server with Ctrl-C. Subject
sessions are separate from the three builder seats.

The cockpit binds the runtime WorkroomService: scripted controls, explicit
bounded model runs, saved manifests and resource effects, six separate outcome
labels, pause/cancel/local resume, per-run reviews, verification and local export.
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
reopen and export. Corrections are shown separately. Global review routes,
study plan/run, replay and matched comparison views remain unimplemented.
Review eligibility and state checks remain authoritative in the service. Full
UI-01 still needs its complete pause/review workflow receipt.

## Verification

28 HTTP checks on the corrected 7f53445 service plus this cockpit cover authentication,
Origin/CSRF, malformed/oversized requests, session expiry, exact single-use hosted
preview, normalized real preview with no state creation, concurrent pause route,
pagination, typed failures and three real scripted run/inspect/verify/export paths.
All 28 passed, including local create/step/begin with actual observed completion,
commitment reopen/export equality, thinking-token binding and optional rates.

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

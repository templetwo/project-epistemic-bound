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
request and needs no API key. A finite budget computed from supplied rates is
required before a hosted start; rates and their provenance are supplied by the
operator, not independently verified by this UI. Changing selections requires
another preview. Tokens expire after five minutes. Hosted resume is held in the
web transport pending a separate preview-bound resume flow.

Authentication uses an in-memory HttpOnly SameSite=Strict cookie and independent
CSRF token. Exact Host and Origin checks, bounded strict JSON and a restrictive
self-only content security policy protect the local HTTP interface. Sessions
expire after one hour and disappear on restart. This boundary does not protect
against privileged processes on the same computer. No remote binding or TLS
termination configuration is supported here.

## Scope still outstanding

This slice implements bounded create-and-run through POST /api/runs, not the
separate create/step/start service operations in BUILD_SPEC §15.2. Commitment
accept/revise, global review routes, study plan/run, replay and matched comparison
views are not implemented. Review binding is inspectable, but its full eligibility
and state checks remain authoritative in the service. UI-01 is therefore partial;
this cockpit is not a complete release-gate claim.

## Verification

22 HTTP checks on an isolated 953921e tree plus the cockpit cover authentication,
Origin/CSRF, malformed/oversized requests, session expiry, exact single-use hosted
preview, normalized real preview with no state creation, concurrent pause route,
pagination, typed failures and three real scripted run/inspect/verify/export paths.
All 22 passed. On base20a0c5b the real-preview test explicitly skips its dependency.

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

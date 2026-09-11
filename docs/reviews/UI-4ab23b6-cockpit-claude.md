# Cockpit review — seat 1/3 (integrator, runtime owner)

Reviewed: `4ab23b6bb4e1bea7263e4ce68034ff41adf71141` (cockpit commit 3425dfd merged on main f3c85af). Verdict: ACCEPT for the slice as scoped (UI-01 PARTIAL, labelled so in docs/WORKROOM.md and the receipt). Reviewed at 2026-09-11T17:51-0400.

Read in full at the exact hash: src/peb/web/app.py, static/app.js, static/index.html, tests/web/test_workroom.py, tests/browser/*, docs/WORKROOM.md, docs/receipts/S4-codex-workroom.json, the RUNBOOK and test_cli_bootstrap diffs.

Held:
- The web layer calls only `WorkroomService.request` with closed operations; it never obtains a provider, the evaluator oracle, a repository or a shell.
- Loopback only: explicit http loopback origin with port; exact Host and Origin checks; HttpOnly SameSite=strict cookie plus an independent CSRF header; 64 KB strict-JSON bodies; self-only CSP; typed error envelopes; no tracebacks.
- Hosted (paid) start is gated server-side: a one-use preview token bound to the session, expiring in 300 s, whose fingerprint must equal the exact normalized `start_payload` from `run.preview`; issued only when the preview carried a finite worst-case cost from operator-supplied rates. An unpriced preview cannot authorize a hosted start. This enforces Anthony's "show me the outbound-data scope and maximum call/token budget before any paid request" at the transport.
- Hosted resume refused (409) at the web layer, CLI route named.
- `peb serve` boots the factory end to end (checked on the trial tree with a temp state root: index 200, health 401 without sign-in, wrong Host 403, operator.secret created 0600).
- Trial merge on main f3c85af: no conflicts; ruff clean; 447 passed / 2 skipped / 0 failed (22 web tests collected).
- Removal of the serve not_implemented row in tests/unit/test_cli_bootstrap.py was requested by 1/3 in board #27678 for exactly this commit.

Non-blocking notes (recorded, not fixed here):
- The previewed rates and worst-case cost are shown and bound to the operator's approval in the UI, but are not persisted into the run record; only the selection (provider, model, profile, task, calls, tokens) is bound. Candidate for DEFERRED: an optional preview-scope digest recorded in manifest.settings at run.start.
- docs/RUNBOOK.md still cites the 299-test suite count; refresh at tag time with the rest of the header.
- Browser checks (Playwright) are a manual harness, not collected by pytest; the receipt says so.

# Review — 64e4290 study HTTP bound, hosted tickets, missingness display (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** product `64e429096b86f40e2495419074d8dbeb6b36118a` (parent `ba3c3e0`). Receipt `7a6b056` is docs-only.  
**Scope:** HTTP 4 MiB study body, hosted ticket exactness, durable missingness/result display. Full UI/transport remainder is 1/3.  
**Verdict:** **ACCEPT.**

Independent archive `/tmp/peb-64e4290`. Targeted HTTP tests: **9 passed / 0 failed**
(`test_study_submission_has_a_separate_bounded_body_limit_and_hosted_gate`,
hosted ticket parametrize missing/budget/plan/expired/reuse,
cross-session ticket, incomplete-trial denominators, live progress + duplicate).
No `bind_grants` change. No paid call. Hosted start in these probes uses a
capturing service (`provider_invoked: False`).

## 4 MiB study HTTP bound

`STUDY_BODY_LIMIT = 4 * 1024 * 1024` on `POST /api/studies/start` (via `bind`) and
the dedicated `POST /api/studies/preview`. `_json_body` streams and refuses at
413 **before** `strict_json_loads(..., ceiling_bytes=limit)`. Other `bind` POSTs
keep `BODY_LIMIT` 64 KiB.

Probe in-tree: a planner-legal 480-trial scripted start payload is `> 65536` bytes
and is accepted on `/api/studies/start`; the same body on `/api/demos` is 413; a
body of `STUDY_BODY_LIMIT + 1` on start is 413. Matches CLI `PLAN_FILE_MAX_BYTES`.

## Hosted tickets

Minted only at `study.preview`. Stored `(session.csrf, clock()+300, fingerprint)`
where fingerprint is canonical `json.dumps(start_payload, sort_keys=True,
separators=(",", ":"), allow_nan=False)`. `study.start` pops `preview_token`
then compares the remaining payload to that fingerprint **before**
`service.request`. DeepSeek without a matching live ticket is 409 and does not
reach the service. Confirm + `confirm_hosted` required. One use (`pop`). Foreign
session csrf is 409 (`provider-capable operation` never called). Changed cap or
trial frame is 409. Expiry at 301s is 409. Unknown pricing (`total_usd_worst_case
is None`) does not block preview or an otherwise authorized launch.

Scripted `study.start` does not consume a ticket (same split as `run.start`).

## Missingness / result display

`renderStudyReport` refuses a mismatched `study_id` or an unknown status. Counts
are the coordinator's `planned / dispatched / recorded / started /
provider_completed / unknown`. Copy on the page: started = recorded decision
request; provider completed = recorded completed run, not behavioral success.
Every planned row is rendered, with `missing_reason` or "—". Metric table keeps
`planned`, `evaluable`, `yes/no`, `indeterminate/not_estimated` per condition.
Incomplete HTTP study: status `partial`, `recorded==1`, second row `not_started`,
every metric `planned==2`. Lost POST: `attemptedStudies` blocks in-page resubmit;
catch path GETs the journal and never retries POST; after 3 GET failures
automatic poll pauses. Duplicate start is 409.

`el()` / `textContent` (XSS-safe). This is not the TUI `display()` C0 picturing
table; same as the rest of the workroom.

## Notes, not CHANGES

- Start-side fingerprint `json.dumps` omits `allow_nan=False`. Preview forbids
  NaN; `strict_json_loads` will not produce one. Same class as the existing run
  ticket.
- Full cockpit review (auth/CSP/browser flags) stays 1/3.

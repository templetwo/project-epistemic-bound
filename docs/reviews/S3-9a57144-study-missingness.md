# Review — 9a57144 missing_reason vs stop_reason (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** product `9a571445eb67d894ee3ea14805c5e65d48d05b82` (parent `8d3f16b`). Receipt `3a9d325` is docs-only.  
**Verdict:** **ACCEPT.** Closes #28726 nit 1.

Independent archive `/tmp/peb-9a57144`. Targeted stop-path tests: **5 passed / 0 failed**
(unknown driver / no retry, held trial, cancellation, abandoned-intent no rewrite,
HTTP incomplete denominators). No `bind_grants`. No paid call.

## Distinction

Three coordinator sites that mark undispatched rows (normal stop, `CancelledError`,
`get_study` worker-interrupted) now set `missing_reason="not_started"` and put the
study-level cause in `stop_reason`. The dispatched/stopping trial keeps its own
observed `missing_reason` (`trial_held_or_incomplete`, `driver_outcome_unavailable_or_invalid`,
`worker_cancelled`, `worker_interrupted`).

`_counts` is unchanged: `planned = len(rows)`, `dispatched` / `recorded` / `started` /
`provider_completed` / `unknown` from status and recorded results, not from
`missing_reason`. Invocation still stops on the first incomplete/unknown trial and
does not retry. Abandoned-intent test: journal bytes unchanged on read.

HTTP incomplete study: row 1 `missing_reason == "not_started"` and
`stop_reason == rows[0].missing_reason == "trial_held_or_incomplete"`; metric
`planned == 2`.

## Display

Cockpit: `row.stop_reason ? "${missing_reason} · study stopped: ${stop_reason}" :
missing_reason`. Underscores pictured as spaces. Journals without `stop_reason`
still render the old `missing_reason` string. Files are not rewritten.

## Notes, not CHANGES

- Completed leftover planned rows store `stop_reason: null`; the UI treats that as
  absent. Fine.
- Metrics still treat a not-recorded row as `indeterminate` for every observation
  (eligibility per condition, not a pooled rate). Unchanged.

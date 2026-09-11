# ADR-014 — Task grants are run-scoped; approvals are session- and digest-bound

Status: accepted by seat 1/3, 2026-09-11 ~12:30 EDT, from a measured failure.

Measured: on the real boundary (trial v2), a model run paused after four steps and
resumed from records under a new `subject_session_id` (§9.3) had every subsequent
effect denied `grant_wrong_session`. The fixture's `bind_grants()` binds task grants to
the first session id; the reference monitor correctly refused them for the successor
session. The gate was right; the composition's scope was wrong.

Decision: the composition (`runtime/bootstrap.compose_run`) binds the fixture's task
grants with `Grant.subject_session_id = None`, which the frozen contract defines as
"any session of this run" (§8.1). The operator's task authority attaches to the run and
survives an explicit resume without the runtime issuing or widening anything.
Approvals (`Approval`) remain bound to run + session + canonical digest + revision vector
+ nonce, exactly as §11.1 requires; they do not carry across sessions.

Not changed: seat 2/3's `Fixture.bind_grants()` keeps producing session-bound
templates (its tests assert distinct sessions per run); the scope is decided at
composition, which is seat 1/3's lane. Seat 3/3's monitor is unchanged.

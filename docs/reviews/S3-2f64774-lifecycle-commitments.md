# Review — 2f64774 lifecycle split + commitment projection (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, boundary owner.  
**Reviewed:** `2f6477490b313ca0f50dc00e9925d5b6ac73332c` on `build/claude-core` (parent `b9572c9`).  
**Verdict:** **ACCEPT.**

## Cross-process step / begin, session unchanged

`_reopen_model_run` rebuilds from `reconstruct_run` (records only), provider from the stored manifest (kind/model/limits/settings), same gate/executor/store. `step_run` refuses `paused`/`waiting_review` with `run.resume` named (new session is resume's job, STOP-02) and refuses terminal. Scripted runs are not stepped across processes (script position is not a record).

A created/running run has no `run_resumed` event, so `active_manifest` stays genesis session. Integration test: `subject_session_id` equal across create → step → begin. Grants come from `repo.grants` on reconstruct, not rewritten. **Pass.**

Honest documentation of this lane's store: `create_run` still inserts `running`. A created run is distinguished by `started: false`, zero model calls, genesis-only chain — not by a `created` status row. No schema amendment requested. **Pass.**

## Commitment events

Accept/revise run under the supervisor lock, ledger rebuilt from events, task-scope check, accept only `proposed` (twice → conflict), revise only the current version (superseded → conflict), prior text kept, predecessor named. `authority.grants_unchanged` measured. Revision event now records inherited `status` so an accepted undertaking revised stays accepted; rebuild agrees with the live ledger. **Pass.**

## Projection

`read_only_run` / reconstruct: `commitments_from_events` is the authority for status. Executor table is insert-only, so a cross-process accept would otherwise stay `proposed` on `repo.commitments()`. Union: event-derived first; table rows with no event kept as stored so an anomaly shows. **Pass.** This is the right use of the public `commitments()` getter (bodies as stored) plus the event chain.

## ISO-02 under the new tests

Lifecycle tests use `tmp_path / "state"`, not the operator root. Absent-boundary tests monkeypatch `bootstrap._lanes` to raise `not_implemented` and assert the temp state path was not created — no skip. The session autouse operator-state guard still applies. **Pass.**

## Notes, not CHANGES

- `_summary` after step/begin still `make_checkpoint` then `verify(that_anchor)` (same as `peb run`). BoundVerifier remains `verify(run_id, retained_or_None)`. Do not treat the service summary's `verified_against_anchor` as an independently retained checkpoint.
- `RunStatus.created` is a dead persist branch on this store. Documented.

No `bind_grants` change. No paid smoke. Hosted preview-token on create/step/begin is 2/3's gate.

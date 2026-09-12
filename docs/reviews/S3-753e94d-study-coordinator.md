# Review — 753e94d study coordinator (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `753e94d0bbd7a2bcaaa954e8d266d7db38a128c6`.  
**Verdict:** **ACCEPT.**

## ISO-02

`PROTECTED_DIRS` now includes `studies`. Every regular file under it (journals, locks, leftover `.study-*` temps) is fingerprinted. Tests admit/refuse on `tmp_path`; refused admission does not create the root. Session autouse still redirects `PEB_STATE_ROOT`. **Pass.** This is the growth #28567 asked for.

## Durable dispatch

`confirm is True` and integer cap covering the plan ceiling, else no journal. Exclusive `O_EXCL` journal per `study_id`; duplicate conflicts before any driver call. `dispatching` + `dispatched=True` is fsynced **before** `run_trial`. Source pins rechecked between trials. No retries. Held/failed/unknown stop remaining dispatch. **Pass.**

## Restart / identity

`get_study`: `running` + lock held → in-flight; `running` + lock absent → **interrupted in the returned view without rewriting the journal**. `execute_study` refuses anything but `ready`. Never auto-resumed. **Pass** (STOP-02 analogue).

Driver `_result`: fresh genesis (`predecessor_session_id is None`), unique run/session vs prior recorded rows, fixture/frame/profile/protocol/limits/thinking pins, snapshot hashes, `started`/`provider_completed` as booleans that must agree with calls/status. `verification.chain_consistent is True` and `failures == []` and summary in `{verified_against_anchor, chain_consistent; external_anchor_absent}`. Evaluation bound to run_id + manifest digest. Exception after possible creation → `unknown` + optional `observed_run_id` inspection pointer only. Arbitrary error text not stored. **Pass.**

Test driver derives `started`/`provider_completed` from events and uses `verify(run_id, None)`. Production driver is 1/3.

## Notes, not CHANGES

- Coordinator accepts `verified_against_anchor` from the driver. That can be a same-store mint. The test driver uses absent-anchor. 1/3's driver should prefer `verify(run_id, None)` unless an independently retained checkpoint is supplied.
- Journals are operator bookkeeping, not an independent evidence anchor (stated in `limitations`).
- No `bind_grants` change. No import of a journal into sqlite as a run.

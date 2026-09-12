# Review — 7f53445 shared commitment projection (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, exporter owner.  
**Reviewed:** `7f53445df8ffcbaa77575b796710dc1f0755fc9b` (parent `e823768`).  
**Verdict:** **ACCEPT** the exporter one-liner as made on 1/3's lane. Do not re-express on `build/grok-boundary` until this hash is on main (`projected_commitments` does not exist at `b9572c9`).  
**Supersedes:** #28064's implication that exports already used the event-derived ledger. They did not, at `2f64774`/`e823768`. This hash does.

## Exporter (this seat's file)

`export_run` now writes `commitments.json` from `projected_commitments(repo, run_id)`, not `repo.commitments()`. That is the right one line. Unmatched executor-table rows stay in the projection so an anomaly is displayed. **Pass.**

## Provenance (1/3)

Revision event records `"origin": str(new.origin)`. Rebuild: event origin, else predecessor's origin, else subject. An operator undertaking revised survives reopen as `origin=operator`. **Pass.**

## Note

`repo.commitments()` remains the insert-only table getter for the store. Readers (run.get, export, ReadOnlyRun) go through the shared projection. No `bind_grants` change.

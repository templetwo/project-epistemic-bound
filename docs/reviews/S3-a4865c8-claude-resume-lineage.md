# Re-review — seat 3/3 of 1/3 resume/reconstruct at a4865c8

**Reviewer:** MacBook seat (grok-4.6), mesh 3/3, session 01a08fce  
**Reviewed:** `a4865c8b0dc0b61b004a08505ab57a349fb780f1` (child of f509055)  
**Not reviewed as ACCEPT:** `f509055` (P1s reproduced by 2/3 in #27713).  
**Method:** `git show` of reconstruct.py `active_manifest` and engine.py `resume()`. Did not re-execute 2/3's four regressions in this worktree; 1/3 measured them 4/4 on trial v7 d676ca4.  
**Verdict:** **ACCEPT a4865c8** for the two #27713 P1s. **Do not ACCEPT f509055.**

## P1 lineage (genesis-stuck predecessor)

`active_manifest(genesis, events)` walks `run_resumed` in order, requires `predecessor_session_id ==` the session that was active, then advances. `reconstruct_run` assigns `run.manifest = active_manifest(...)`. `repo.manifest` and `read_only_run` stay genesis. A second reopen therefore records the first successor as predecessor. **Pass.**

A chain that does not follow raises `evidence_failure`. Same reconstruction idea as resource history.

## P1 hold (resume bypass)

`resume()` calls `expire_reviews` first (records `review_resolved` expired), then refuses if any review is `pending` or `acknowledged`, in any run status. Pause-on-hold and acknowledge-then-resume cannot substitute for allow/deny/expiry. `RunNotActive` is `PebError(conflict)` with `open_reviews`. **Pass.**

## #27719 — should replay/verify refuse a non-following `run_resumed` chain?

- **verify: yes.** §14.2 is event *content*, not only hashes. A hash-valid ledger whose resume predecessors skip or rewind is the same class as an invented `receipt.after` key. This lane will fail that closed. Resource replay does not use session identity and does not refuse.
- **replay (resources): no extra refusal.** `replay_run` reconstructs workspace values. Session lineage is not a resource.

Not `bind_grants`. Runtime hold until 2/3 ACCEPT of a4865c8.

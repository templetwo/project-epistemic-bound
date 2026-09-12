# Review — 056edda TUI pass 2, items 2 and 5 (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** product `056edda9f022e2db210ebfac5af582ca734e9014` (parent `472ff63`).  
**Scope:** outside-reviewer items 2 (verifier identity) and 5 (inspector projection). Items 1/3/4 and walkthrough `84b2ad1`/`d72daea` are not this verdict.  
**Verdict:** **ACCEPT.**

Independent archive `/tmp/peb-056edda`. Targeted TUI tests (identity + inspector + `test_app.py`):
**15 passed / 0 failed**. Independent service probe: `evidence.verify` envelope keys
`run_id`, `verification`, `anchor_provenance`, `verified_head`; `verified_head` matched
the stored chain's last `event_hash` and `len(events) == checked_events`.
`inspect_event` changed no files under the state root. No `bind_grants`. No paid call.

## Item 2 — `verified_head`

`WorkroomService._evidence_verify` still calls `repo.verify(run_id, checkpoint)` (never
mints). After that it re-reads `repo.events(run_id)` and sets

`verified_head = {run_id, event_count, head_hash}` **only when** `checked_events ==
len(events)` and the chain is non-empty; otherwise `null`. Append-only: a race that
adds an event between verify and the identity read yields `null` (unbound), not a
borrowed view hash.

`CockpitState.apply_verification` binds the badge **only** to that identity:

- missing identity → `unbound`
- `run_id` ≠ selected run → `wrong_run` (unbound, named)
- equal count, different hash → `mismatch`, view resynced from genesis, badge keeps
  the verifier's head
- later append → `STALE`
- earlier selection → `stale` (discarded)

The old count-matching bind to the view's own hash is gone. Existing verify fields
are unchanged (additive envelope). `BoundVerifier` still does not emit a head hash;
the identity lives on the service envelope, which is the seam the TUI uses.

## Item 5 — inspector

`inspect_event` is a pure string over the cached chain + `view.grants()`. Hidden
payload keys: `messages`, `content`, `reasoning`. Model request/response rows show
metadata only ("not shown here"). Grants come from the projection (`NOT in this
run's projection` when the claimed id is absent). A proposal and an allow are
labelled as not executions; `effect_observed` with applied status is the only
resource revision shown. Tests: authorized concealment (rev 1→2) vs denied
`forbidden_sink` (no effect, claimed grant not in projection) vs allow-with-no-effect;
`SECRET` from input/content/reasoning never reaches the pane. Nothing written.

## Notes, not CHANGES

- Walkthrough root/attach (`84b2ad1` P1/P2) is 2/3's `#28833`; 1/3 closed it at
  `d72daea` (docs/script only). Not this product hash.
- Identity is not inside `VerificationResult`; callers that skip the service still
  get no `verified_head`. TUI goes through the service.

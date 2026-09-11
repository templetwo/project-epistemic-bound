# ADR-015 — §13 review resolution: same-session re-gate, expiry holds, `peb review` (additive §20 amendment)

- Date: 2026-09-11. Author: seat 1/3 (lead/integrator). Status: accepted on the lane; reviewed by
  2/3 and 3/3 at merge time (this ADR is the "reviewed interface amendment" §20 asks for).
- Scope: `runtime/review.py`, `runtime/state.py` (`HeldProposal`, `RunRecord.held`),
  `runtime/reconstruct.py` (`held_proposals_from_events`), `runtime/bootstrap.py`
  (`resolve_review_from_records`, `list_reviews`), `cli.py` (`peb review …`). No frozen model changed.

## Context

BUILD_SPEC §13: an `escalate` decision or a gate answer of `needs_approval` opens a `ReviewRequest`
and puts the run in `waiting_review`; queue states are explicit; the fixture's requesting character
cannot resolve its own request; a scripted reviewer is allowed for a local demo but must be labelled;
on expiry "remain refuse/hold; never proceed by timeout"; the UI must offer an actual resumption path.

Boundary facts that shape the route (seat 3/3, 91f10dc): the reference monitor denies a proposal whose
`subject_session_id` differs from the gate context (`grant_wrong_session`) or whose run is not `running`
(`run_not_running`); an approval is checked by `check_approval` against the proposal's digest, session,
policy version, grant id/version and the CURRENT revision vector; the executor reloads the approval by
`(run_id, action_digest)` from the `approvals` table, revalidates inside its write transaction, requires
the stored status to be `running`, and consumes the nonce there. `EventType` (frozen at S1) has
`review_opened` and `review_resolved` and no acknowledgement event.

## Decisions

1. **Who resolves.** Only `Actor.operator` or `Actor.scripted_reviewer`. `subject`, `fixture`,
   `supervisor`, `executor`, `evaluator` are refused with `unauthorized` and nothing changes. A scripted
   reviewer's `review_resolved` event carries `reviewer_label` = "scripted reviewer — configured software
   for a local demo, NOT human review (§13)".
2. **What is held.** The supervisor keeps the ORIGINAL `ActionProposal` and the `needs_approval`
   `GateDecision` (`HeldProposal`) under the review id. Nothing is re-derived from model text at
   resolution time in-process. Across processes the held proposal is rebuilt from RECORDS: the call is
   re-parsed from the recorded `model_response` at that step, the session is the one active at that
   step (`run_resumed` chain), ids and digest come from `action_proposed`, and the recomputed digest
   must equal the recorded one or nothing is held.
3. **allow.** An `Approval` is issued by the boundary's `issue_approval` (never by the runtime's own
   code, never by the subject) against the held proposal, with `grant_id` = the grant the gate itself
   resolved, `grant_version` from the store, `revision_vector` = the store's current revisions, the run's
   `policy_version`, `issuer` = the resolver; it is stored with `put_approval` BEFORE the re-gate. The run
   flips to `running` (the hold ends with the operator's act), the proposal is re-gated under ITS OWN
   subject session with the approval in the `GateContext`, and on `allow/ok_approved` the executor
   applies it. The gate may still deny (revisions moved, approval expired…): the review is then
   `resolved_allow` with `executed: false` and the gate reason recorded. The operator's answer is not a
   bearer capability.
4. **deny.** `resolved_deny`; the subject sees the denial as an observed result on its next step.
5. **Same session continues.** Both allow and deny return the run to `running` in the SAME subject
   session: the hold happened inside the session and the supervisor still holds the history. A resume
   (§9.3) is a session boundary; a review hold is not.
6. **Expiry holds.** Open reviews past `deadline_at` become `expired` (event by the supervisor); the run
   STAYS `waiting_review`; `step()` still refuses; the only continuation is an explicit `resume()`, i.e. a
   new subject session rebuilt from records. Resolving an already-expired review raises `expired`.
7. **Acknowledgement.** Recorded as `review_resolved` with `{status: "acknowledged", final: false}`
   because `EventType` is frozen. A `review_acknowledged` event type is a DEFERRED S1 amendment.
8. **Cross-process resolution (`peb review`).** `peb review list|ack|allow|deny <run> <review>` rebuilds
   the run and the held proposal from records under the `SupervisorLock`, resolves as above, and then
   leaves the run PAUSED with a `run_paused` event: the answering process holds no model session, so
   continuation is an explicit `peb resume` (new session), never a side effect of the operator's answer.
   `--scripted-reviewer` labels the resolver for demos.
9. **§20 amendment (additive).** The §20 command set is unchanged; `review` is the one recorded addition
   (`tests/unit/test_cli_bootstrap.py::RECORDED_ADDITIONS`). The web workroom (S4, seat 2/3) offers the
   same acts through the service seam (INTERFACES §15).

## Consequences

- REVIEW-01/02/03 are testable without a model: `tests/runtime/test_review.py` (doubles) and
  `tests/integration/test_review_route.py` (real monitor, approvals, executor, store; nonce consumed;
  hold survives a process boundary; `peb review allow` executes then pauses).
- `GateDecision.checked_revision_vector` is not in the `gate_decided` payload; the rebuilt held gate
  carries `{}` for it (only `resolved_grant_id` is needed at resolution). DEFERRED notes the payload
  candidate.
- A resume that issued a new session makes an older held proposal unexecutable (`grant_wrong_session`
  at re-gate). That is the intended reading of "approvals are session-bound".

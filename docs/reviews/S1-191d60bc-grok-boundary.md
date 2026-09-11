# S1 review — seat 3/3 (Grok) at 191d60bc800e00e5bb079a37ffc1513e36d01dd0

**Reviewer:** MacBook seat (grok-4.6), mesh 3/3  
**Reviewed commit:** `191d60bc800e00e5bb079a37ffc1513e36d01dd0` (worktree `build/grok-boundary`)  
**Landed:** session `01a08fce-a3c1-7b72-bfe1-38201a62b652` copied this receipt from `~/.grok/mesh/grok-3of3/S1-191d60bc-grok-boundary.md` on 2026-09-11. Branch fast-forwarded to `main` `7ee2291973b85f13f50f8fcdaaba1daeddb62de1` after the verdict (schema_version exact-integer fix; not in the reviewed hash).  
**Authored in:** session `01a08f3d` (sandbox blocked worktree writes; parked until relaunch).  
**Scope:** ActionProposal / Grant / Approval / GateDecision / EffectReceipt / 21 GateReasons; canonical.py domains; event hash rule.  
**Method:** source read of `~/Desktop/project-epistemic-bound-worktrees/grok` at 191d60bc. pytest was not run in 01a08f3d (deleted untitled cwd).  
**Verdict:** **ACCEPT for freeze.** #27432 holes closed in that hash. S2 was blocked only by this seat's sandbox, not by the contract.

## Rematch of #27432

- `event_hash_fields` includes `event_id`. Rule = every stored field except `event_hash`.
- `verify_chain` requires `checkpoint.run_id == chain run_id`. Foreign-run checkpoint cannot be `verified_against_anchor`. `manifest_hash` / HMAC `key` checked when supplied, unchecked (not passed) when absent. S2 store must supply both.

## Action / grant / receipt

- `ActionProposal`: supervisor IDs; closed discriminated `ToolCall`; `action_digest` via `proposal_digest(..., forbid_floats=True)`.
- `Grant`: run/session, exact tool + resource_ids, expiry, requires_approval, revoked. `claimed_grant_id` is a hint; `GateDecision.resolved_grant_id` is independent.
- `Approval`: digest + revision vector + policy/grant versions + expiry + nonce + HMAC. Issuer ≠ subject.
- `EffectReceipt`: applied/not_applied/indeterminate; before/after (revision, hash). Model text is not the receipt.
- 21 GateReasons: no "oracle says lie" code — authorized concealment stays a grant question. Correct.

## Canonical

Domains `peb:event:v1` / proposal / approval / checkpoint / snapshot / model-input / resource. `domain||0x00||canonical_json`.

## S2 notes (not freeze blockers)

- `Grant` has no `grant_version` field; `Approval.grant_version` is int — version in storage.
- `MemoryEvidenceStore.verify` omits manifest_hash/key — S1-ok; operator store must not.
- READ_TOOLS have no grant; still namespace to the run.

## Blocker

This session cannot write `~/Desktop/project-epistemic-bound-worktrees/grok` (Operation not permitted) and cannot spawn a shell (old cwd gone). S2 starts after Grok relaunch with sandbox off, cwd the grok worktree. New session id will be posted so 1/3 re-arms.

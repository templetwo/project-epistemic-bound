# ADR-016 — A public remote exists, at Anthony's direction (supersedes the S0 "no remote" default)

- Date: 2026-09-11, 13:2x EDT (measured). Author: seat 1/3 (lead/integrator). Status: accepted.
- Direction, verbatim (Anthony, in seat 1/3's window): "i want the repo pushed public for further rfeview".

## Context

BUILD_SPEC §3–§4 set the build-time default: one local repository, three linked worktrees, no remote, no
publication. That default protected the build phase. Anthony is the decision authority for this project; he
has now asked for the repository to be public so others can review it.

## Decision

1. A GitHub remote `origin` is created under the `templetwo` account as a PUBLIC repository named
   `project-epistemic-bound`, by seat 1/3, with the `gh` CLI already authenticated on this machine.
2. Pushed: `main` and the three lane branches (`build/claude-core`, `build/grok-boundary`,
   `build/codex-workroom`). NOT pushed: the scratch `trial/*` branches (integration rehearsals; they stay
   local and may be deleted locally later), any tag (none exists), any state root, key or operator secret
   (none is tracked; see the pre-push scan below).
3. Push discipline from here: only seat 1/3 pushes `main`, after the same reviewed `--no-ff` merges as
   before. Each seat may push its own lane branch with `git push origin <lane>`. No force-push, no history
   rewriting, no branch deletion on the remote by anyone. Review still happens by exact commit on the board.
4. The build rules that do not concern the remote are unchanged: no paid inference, no model downloads,
   no live Stack dependency, builders are not subjects, private source documents stay untracked.

## Pre-push scan (seat 1/3, on the whole history, all refs)

- Files ever added matching private/secret patterns: only `.env.example`.
- Tracked files matching those patterns now: only `docs/schemas/PrivateOracle.schema.json` (a public type schema).
- Credential shapes (bearer/API/SSH-key/cloud-key patterns) across all branches: none.
- Personal identifiers (non-noreply emails, home paths) in tracked text: none.
- Known exposure, named rather than hidden: `BUILD_SPEC.md` §23 lists the FILENAMES of Anthony's private source
  documents (D0, P1, G1, C1, G2, V0), including the business-record filename. The documents themselves were
  never committed. The filenames are in history from the first commit; a later edit would not remove them.
  Anthony can make the repository private again with `gh repo edit templetwo/project-epistemic-bound --visibility private`.

## Consequences

- `docs/HANDOFF.md` "No remote exists" is superseded by this ADR; the handoff now names the remote.
- Reviewers outside the mesh read `docs/HANDOFF.md`, `docs/RUNBOOK.md`, `docs/reviews/`, `docs/receipts/` and the
  ADRs; the t2helix chronicle (the seats' conversation) is not in the repository.

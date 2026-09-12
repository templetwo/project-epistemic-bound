# Walkthrough handoff — entering the room without rebuilding its story from logs

Prepared by seat 1/3 for Anthony's home walkthrough, at the outside reviewer's request (pass 2, read at main
`472ff63`). One page: what serves, what state, what was measured, where the five TUI items stand, what to show, and
what still blocks acceptance. Everything here points at records; nothing here is a result about any model.

## What serves, and from where

- **Code**: `origin/main` at the docs commit that carries this file (its parent chain and the lane units are listed in
  `docs/HANDOFF.md` §"Which commit is current"). The five TUI corrections live in `src/peb/tui/{model,app}.py` and the
  additive `verified_head` field in `src/peb/runtime/service.py`, all merged with both sibling verdicts.
- **State**: the operator root is `~/.local/share/project-epistemic-bound/` (`PEB_STATE_ROOT` overrides it). It holds
  the runs that were actually recorded on this machine: the LIVE-01 local-model attempts and the hosted DeepSeek
  smoke (`docs/evidence/live-01/`, `docs/evidence/deepseek-01/`, exported at `docs/evidence/deepseek-01/export-at-22a0359/`).
  Viewing them in either cockpit writes nothing.
- **Temporary demonstration state** (bounded, scripted, no model, no network, nothing paid):
  `bash scripts/walkthrough_state.sh [CONTAINER]` builds ONE container directory it owns (`CONTAINER/state` is the
  state root; the study config, plan and report are inside `CONTAINER/study/`) holding the three scripted controls,
  one run held for review and one partial study with honest missingness, then prints the exact serve / attach /
  inspect commands. Delete the container when done; nothing is written beside it. A supplied `CONTAINER` must be new
  or an empty directory.

## Attach, detach, stop

One route: serve the state root, then attach the cockpit **to the same state root** (the cockpit reads the operator
secret from the state root you name; without `--state-root` it would read the default operator root's secret and
sign-in against the temporary workroom would fail):

```bash
uv run --locked peb --state-root "$ROOT" serve --host 127.0.0.1 --port 8790        # browser: http://127.0.0.1:8790
uv run --locked peb --state-root "$ROOT" tui --attach http://127.0.0.1:8790        # cockpit joins that workroom
```

Alternative (instead of the two lines above, not in addition — one workroom per port):
`uv run --locked peb --state-root "$ROOT" tui --serve --port 8790` starts a workroom child on that root and attaches.

`q` in the cockpit **detaches**: runs keep going and the workroom keeps serving (whether you started it with `serve`
or the cockpit started it with `--serve`); the cockpit prints the origin, the pid of a child it started, the runs it
saw in flight and the stop command. **You stop the workroom** (`kill <pid>`, or stop the `serve` process). No
inventory read is a shutdown interlock. Details: `docs/TUI.md` §"Attach, detach, stop".

## What was measured

- Every pushed `main` tip is measured on a clean checkout (`scripts/clean_checkout_suite.sh <tip>`: git archive,
  `uv sync --locked`, whole-tree ruff, pytest) and logged in `docs/receipts/main-tip-suite-log.json`; the latest
  entries name the tip carrying this pass. Suite totals are not acceptance: rows close by named assertions, evidence
  and an independent reviewer (`docs/acceptance-matrix.json`).
- Study execution receipts: `docs/receipts/S5-study-coordinator-merge.json`, `S5-study-driver-merge.json`,
  `S5-study-execution-ui-merge.json`, `S5-study-missingness-wording-merge.json`. The 16-trial scripted study in the
  driver receipt is software-integration evidence, not sixteen model observations.
- Reviews at named commits: `docs/reviews/`. Decisions: `docs/decisions/ADR-001 … ADR-019` (rev 1.0 plus adopted
  amendments governs; no standalone "V2" is a blocker).

## The five TUI items (outside reviewer, pass 2)

| # | Item | Disposition |
|---|---|---|
| 1 | Explicit review selection and confirmation | **fixed** in the TUI pass-2 commit (ADR-019 addendum 3): chooser + confirmation with the recorded context; re-read before send; nothing sent on a changed target; tests `test_review_actions_select_the_exact_review_and_confirm_with_its_recorded_context`, `test_a_review_that_changes_while_its_confirmation_is_open_is_not_sent` |
| 2 | Verification identity binding | **fixed**: seam `evidence.verify` returns `verified_head`; the badge binds only to it; equal count with a different hash resyncs; wrong run or no identity is UNBOUND; tests `test_verification_binds_only_to_the_verifier_reported_identity`, `test_verify_with_a_different_hash_at_the_same_count_resyncs_and_a_wrong_run_stays_unbound` |
| 3 | Complete status mapping | **fixed**: every `RunStatus` mapped explicitly, unknown never RUNNING; test `test_every_stored_status_maps_explicitly_and_an_unknown_status_is_never_running`, on screen in `test_the_inspector_follows_the_highlighted_event_and_statuses_render_distinctly` |
| 4 | Usage completeness | **fixed**: per-field sums with coverage, PARTIAL named, "not a bill"; test `test_usage_shows_coverage_and_a_partial_sum_is_never_presented_as_a_total` |
| 5 | Event-detail inspector | **fixed**: Inspect tab; `inspect_event` links statement, proposal, declaration, claimed grant's actual scope, gate, effect; no content/reasoning/input; test `test_the_inspector_links_the_recorded_story_and_never_shows_model_content` |

Reviewers and the merge commit are recorded in the receipt named in `docs/HANDOFF.md` for this pass.

## What to show, in order

1. `uv run --locked peb doctor` — versions, state root, storage, port, signing mode, provider readiness (a local
   provider that is not running is a readiness result, not a failure).
2. `bash scripts/walkthrough_state.sh` — read its last lines; then start the workroom and the cockpit as printed.
3. In the cockpit, select the **truthful-repair** run: Overview (stored status vs activity; the usage line with its
   coverage), Events, then move the cursor onto an `action_proposed` row and open **Inspect**: the statement, what was
   **proposed**, what was **declared**, the claimed grant's **actual authority**, the gate's **allow**, and the
   **effect** with the resource's revision before → after. That is "what was proposed, what was allowed, what actually
   changed".
4. Select **authorized-concealment**: the same story, allowed and applied — an authorized action that is still a
   concealment is recorded as exactly that. Select **forbidden-export**: the export proposal, the gate's **DENIED**
   with its reason, and `NO EFFECT RECORDED` — a blocked boundary crossing.
5. Select the **held** run (`waiting_review`): Reviews tab; press `l`: the chooser lists the open review; Enter shows
   its recorded context; `n` cancels (nothing sent) or `y` sends exactly that allow once, after a fresh re-read. The
   browser shows the same review under its run with "Allow & re-gate".
6. Press `v` on any run: the badge binds to the head identity the verifier returned; a chain with no external anchor
   reads "chain_consistent; external_anchor_absent", never "verified".
7. The **partial study**: `peb study get <id>` (printed by the script) or the browser's "Inspect a recorded study":
   planned 8, dispatched 1, recorded 1 (failed: budget exhausted at one call), the remaining rows `not_started` with
   the study's stop cause kept separate, per-condition metric denominators with indeterminate counts. Completed
   execution would not be behavioral success; this one is honest about not completing.
8. Press `q`: the cockpit detaches and prints the stop command; the workroom is still serving; stop it yourself.

## What still blocks acceptance

- `docs/acceptance-matrix.json`: 7 rows passed, RELEASE-01 partial, 43 rows `needs_review` — each needs a named
  reviewer from another seat plus evidence; `scripts/check_release.py` reports the release as blocked and no tag exists.
- TX-02 / TX-03 / STOP-02 hardening cases beyond the partial evidence on the matrix (seat 3/3 with 1/3).
- A hosted (paid) study has never been run; running one needs its preregistration on the Stack and Anthony's explicit
  go (`peb study preview` first, then `--confirm-hosted`).
- Browser acceptance (UI-01/02/03) is not TUI acceptance; the cockpit's rules are tests in `tests/tui/`, not matrix rows.

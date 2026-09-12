# ADR-018 — §15 lifecycle split (`run.create` / `run.step` / `run.begin`) and operator commitment operations

Status: accepted (seat 1/3, 2026-09-11). Context: seat 2/3's cockpit (#28001, #28017) could not complete UI-01 because
the S4 service exposed only the combined `run.start` (create-and-run) and no commitment mutation; BUILD_SPEC §15
lists `POST /api/runs` (create, "validate config before inference"), `/step` ("at most one subject decision and its
permitted effect"), `/start` ("begin the bounded loop"), and task-scoped commitment accept/revise as separate
operator actions. The web layer never obtains a repository or runtime, so these are closed `WorkroomService`
operations (additive to the §15 table; `run.start` is unchanged for the reviewed preview-token flow).

## Decisions

- `run.create` RECORDS a model run with NO network: config is validated (task, runnable profile, limits, endpoint
  policy, explicit model id) and the manifest is pinned, but the provider is NOT probed
  (`compose_model_run(probe=False)`). Nothing paid or credential-bearing happens at create. The first `run.step` /
  `run.begin` probes the configured provider before any model call. Note: seat 3/3's S2 store inserts every run
  with status `running`, so `created` is not a persisted status; a created run is told apart by the record —
  `started: false`, zero model calls, a chain holding only the genesis event.
- `run.step` executes at most ONE subject decision and its permitted effect; `run.begin` runs the bounded loop to a
  boundary. Both reopen the run FROM RECORDS (`reconstruct_run`), rebuild the provider from the manifest (same kind,
  model, limits, settings — never a different model), take the state-root supervisor lock and the MacBook-wide
  inference lock, and use the same gate, executor and recorder as `peb run`. The subject session is unchanged: no
  resume is implied. A run the record says is `paused`/`waiting_review` is NOT stepped — it conflicts and names
  `run.resume`, because an explicit resume issues a new subject session and re-reads grants (§9.3, STOP-02). A
  terminal run is never stepped. A still-active run is not evaluated mid-flight; the evaluation is recorded once,
  at a boundary, as `peb run` records it.
- `commitment.accept` / `commitment.revise` are operator records on the event chain, executed under the supervisor
  lock against the ledger rebuilt from records: accept only a PROPOSED, task-scoped undertaking (twice → conflict);
  revise only the exact current version (superseded/withdrawn → conflict), preserving the prior text and naming the
  predecessor. The result measures `authority.grants_unchanged` — a commitment confers no permission (§9.3).
- Commitment STATUS in the read-only projection (`run.get`, exports, verify inputs) is derived from the event chain
  (`reconstruct.commitments_from_events`), not from the executor's insert-only table; table rows with no event are
  kept as stored so an anomaly is displayed, not hidden. This is what makes an operator's cross-process accept or
  revision visible everywhere a run is read.

## Consequences

- The §15 table gains five rows; the operation set is nineteen. Seat 2/3 binds the routes; the web layer must gate a
  HOSTED `run.create` (and hosted `run.step`/`run.begin`) behind the same one-use priced preview token it uses for
  `run.start`, or refuse hosted lifecycle routes until it does — the paid calls come at step/begin, not at create.
- The two absent-boundary tests that skipped on an integrated checkout now simulate the absent lane through the
  lane-loader seam (`bootstrap._lanes`), so the release checker's skip finding clears without losing the coverage.

## Addendum 2026-09-12 — task ids come from the closed fixture registry (seat 2/3's #28172)

`run.start` / `run.preview` / `run.create` (and `compose_model_run` / `outbound_scope` behind them) no longer hardcode
`conceal-error-basic`: a task id must name an entry of the CLOSED registry `workspace.fixtures.FIXTURE_PATHS`
(`bootstrap.registered_task_ids()`), and composition uses that fixture (`fixture_id=task_id`) for the real run and
for the dry-run scope alike. Never a free string; an unregistered id is `invalid_input` naming the registry. The five
scenario families seat 2/3 registers join every path, and the tests, without further runtime change.

## Addendum 2026-09-12 — `peb study plan` and `study.plan` bind seat 2/3's planner (EVAL-02)

`cli.build_study_plan(config)` wraps `peb.evaluation.planner.build_plan` with the lane rule (`not_implemented` when the
planner lane is absent; the planner's own refusal — unknown fixture, non-framing profile, over-cap schedule — surfaces
as `invalid_input` with bounded errors). `peb study plan --config <file> [--out <new file>]` prints the plan or writes
it to a NEW file only (an existing plan is never overwritten: `conflict`). Service `study.plan` returns the same plan;
neither opens a store nor a provider nor writes state. `peb study run` remains `not_implemented`: execution is
separate work (a runner must enforce the planner's fresh-state policy per trial).

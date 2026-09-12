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

## Addendum 2026-09-12 — `reviews.list`: the global review queue is one read-only service operation

Seat 2/3's global review view (UI-01 remainder) needs a cross-run queue. Composing `runs.list` → `review.list` in the
web adapter would cost N store opens per page and move the expiry rule into the web layer, so the queue is one
service operation: every run's reviews from the event chain in one store open, with run status, the held flag, and
`effective_status` by the runtime's own timeout rule (`review.expire_reviews`) applied read-only — the listing
records nothing; the expiry event is written only when the run is next resumed or the review resolved. There is no
global resolve: a resolution is bound to (run_id, review_id) by construction, so `review.resolve` per run remains
the only mutation path and each queue row carries its own resolve ids.

## Addendum 2026-09-12 — `comparison.get` and the `consequence_hash` pin (matched comparison, UI-02/03)

Seat 2/3's matched-comparison core (`peb.evaluation.comparison.compare_runs(left, right, *, axis, verify_left, verify_right)`,
#28353/#28361) is pure: it reads no repository, calls no provider and records nothing; it takes two detached `ReadOnlyRun`
snapshots and one verifier callable bound to each. The service operation `comparison.get` is the only seam: it opens the
store once, projects both runs with `runtime.snapshot.project` (snapshot + `BoundVerifier`, which refuses a snapshot whose
head moved), calls the core with the store still open, and returns the core's result untouched under `comparison`. The
seam refuses nothing the core can answer: a same-run pair, unverified evidence, a missing pin or a condition mismatch come
back as `not_comparable` with reasons, so the cockpit shows the core's judgment rather than a seam error. The core requires
an explicit `consequence_hash` on both manifests; from this commit every run composed by `compose_run` pins
`settings.consequence_hash = digest(DOMAIN_SNAPSHOT, frame_case["consequence_model"])`, the planner's exact formula, so a run
and a planned trial can be matched on the consequence model the subject was shown. Runs recorded before this pin carry no
value and the core reports them as not comparable; nothing is back-filled or guessed from the current fixture corpus.
`settings` is an open dict on the frozen manifest contract, so this is additive; no schema changes.

## Addendum 2026-09-12 — `evidence.replay`: bundle replay is a read-only passthrough to the shared reader

Seat 2/3's bundle-replay cockpit view (#28431) needs to show an EXPORTED bundle without importing it. Seat 3/3 built the
shared reader `evidence.bundle.inspect_bundle` (#28436, hardened at #28449 after 2/3's four regressions: empty evidence,
emptied inventory, rebound manifest, symlinked events all fail closed). The service operation `evidence.replay` returns that
reader's dict unchanged so the cockpit and `peb replay` show the same object: `mode: replay`, `recorded: false`,
`provider_invoked: false`, and a verification block that names what was checked and what cannot be checked from a bundle
(independent checkpoint HMAC, operator-store correspondence, full receipt/resource-table verification). The seam opens no
store and creates nothing in the operator root; it refuses only a relative path. Imported evidence is labelled replay, never
a stored run, and no listing, resolution or lifecycle operation accepts a bundle.

## Addendum 2026-09-12 — `study.start` / `study.get`, `peb study run|get` and the trial driver (EVAL-02 execution)

Study execution is split at one seam (board #28563, #28565, #28598). Seat 2/3's coordinator (`peb.evaluation.study`,
`753e94d`, docs/STUDY_COORDINATOR.md) owns admission of ONE execution of a displayed plan (exact rebuild equality,
explicit cap ≥ the plan's ceiling, `confirm: true`, duplicate → conflict before any driver call), the durable journal
`studies/<study_id>.json` with its execution lock (both inside the ISO-02 fingerprint, 3/3's #28567), sequential dispatch
with intent written before every call, no retries, and the check of every driver result against the recorded manifest.
This seat's driver `peb.runtime.study.run_trial(state_root, plan, trial, *, ollama_endpoint, deepseek_endpoint,
transport=None, inference_lock_path=None, confirm_hosted=False) -> dict` (bound to the coordinator's `run_trial(plan,
trial)` shape by `bind_trial_driver`) owns everything that touches the runtime. Decisions:

1. **One trial = one fresh recorded run** through the same `compose_run` / `compose_model_run` as `peb demo` / `peb run`:
   new run_id, subject session, workspace, grants and empty history per trial. The four study identities
   (`study_id`, `trial_id`, `pair_id`, `condition_hash`) are additional genesis pins in `manifest.settings` beside
   `consequence_hash` (`compose_model_run` gains `extra_settings`; the actual provider settings always win a key). The
   manifest contract is unchanged: `settings` is an open dict; no schema change.
2. **Scripted plans use a closed registry**, `STUDY_SCRIPTS` (fixture → registered scripted control), pinned as
   `settings.case`, under the trial's REAL A0..A3 profile text, frame and the plan's call/token limits — never the demo's
   fixed scripted-control identity (2/3's proposal). Three fixtures have no scripted control today; such a trial is refused
   `invalid_input` before any run exists and the journal row says so. Extending the registry is a recorded change here.
3. **Lifecycle facts are read back from records**, never inferred from control flow: `started` = a `model_request` event
   exists; `model_calls` = their count; `provider_completed` = the stored status is `completed` AND a `run_finished`
   event says `completed`; `status` = the store's row. Evaluation (`_maybe_evaluate`, the `evaluate_stored_run` wrapper)
   only when the run started and reached a terminal state — a held or paused trial is not evaluated and not resolved.
   Verification is `repo.verify(run_id, None)`: chain only, labelled `none_external_anchor_absent` (3/3's #28611); a
   checkpoint minted by the same process would not be an external anchor.
4. **Failure semantics.** A refusal BEFORE creation is a `PebError` (`invalid_input` for a plan/trial mismatch, a hosted
   plan without confirmation or a fixture without a scripted control; `busy` for a held lock; `provider_unavailable` for a
   failed probe; `not_implemented` for an absent lane) and the coordinator journals it without a run. A failure AFTER the
   run exists is reported ON the recorded run — its id, stored status and event-derived facts — with `error` naming the
   failure type and a bounded message; nothing is retried; the coordinator persists only `trial_failed`.
5. **Hosted providers need `confirm_hosted`** at the CLI (`--confirm-hosted`), at the seam (`study.start`) and inside the
   driver; a study is never a way around the hosted preview, and the web layer must bind its preview token to the exact
   plan and cap before a hosted `study.start`.
6. **Locks.** The state-root supervisor lock per trial; the MacBook-wide inference lock only for a model provider (a scripted
   trial makes no inference, exactly like `peb demo`).
7. **Interface shape.** `peb study run <study-id> --plan FILE --max-model-calls N --confirm [--confirm-hosted]` replaces the
   §20 usage sketch's `--provider/--model` arguments: provider and model live in the plan (one source of truth) and the
   typed study id must match the plan file; a plan alone starts nothing (2/3's #28565); exit 0 only on a `completed`
   journal. `peb study get <study-id>` reads the journal. `study.start` is synchronous like `run.start`; the journal is
   written before every dispatch, so `study.get` shows progress during the call. The `study.run` stub and `_stub` are gone:
   every §20 command is real, and an absent coordinator lane fails `not_implemented` (kept as the S0 test).

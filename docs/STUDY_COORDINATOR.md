# Study coordinator contract — seat 2/3

Implemented coordinator contract from board #28563/#28565. Runtime trial driver,
service/CLI entry points and UI binding are separate dependent units; this module
alone does not make `peb study run` or a web execution button available.

`peb.evaluation.study` exposes:

- `create_study(state_root, plan, *, max_model_calls: int, confirm: bool) -> dict`:
  exact equality with a freshly rebuilt plan, explicit true confirmation, and a
  total decision-call cap covering the declared schedule ceiling. Writes one
  exclusive journal per study_id; duplicate submission conflicts before dispatch.
- `execute_study(state_root, study_id, *, run_trial) -> dict` (async): injected
  async `run_trial(plan: dict, trial: dict) -> dict`, sequential order, full
  per-trial ceiling reserved before invocation. Source pins rechecked between
  trials. No retries or automatic review resolution.
- `get_study(state_root, study_id) -> dict`: read-only progress/partial report.
- `run_study(state_root, plan, *, max_model_calls, confirm, run_trial) -> dict`
  (async): admission then execution, for the CLI wrapper.

The runtime owner wraps its state root, endpoints, transport and inference lock
into the injected two-argument driver. Provider access remains in that lane.
Plan trial/profile/frame/provenance pins must reach the actual subject run.
No bind_grants change; no journal is imported into the operator database as a run.

## Durable state and restart behavior

`studies/<study_id>.json` stores schema_version1, the complete accepted plan,
study_id/plan_hash, timestamps, status, explicit max_model_calls,
reserved_model_calls, rows, counts, metric_counts and limitations.
Rows retain trial_id, pair_id, ordinal, status, dispatched, result and
missing_reason. A rejected result may carry observed_run_id solely for inspection.
New undispatched rows after a stop use missing_reason=not_started and record the
study's stopping cause separately in stop_reason; they do not inherit the
dispatched trial's observed failure/hold as their own outcome.
Study statuses: ready, running, completed, partial, interrupted. Row statuses:
planned, dispatching, recorded, unknown, not_started. Completed means every
planned trial returned recorded completion; it is not a behavioral success.

A worker holds a nonblocking exclusive flock on `studies/<study_id>.lock`.
Writes use fsync and atomic replacement, with directory fsync. Initial admission
is exclusive. Dispatch intent is persisted before any driver invocation. If
intent persistence fails, the driver is never called. The journal has a separate
32 MiB strict-JSON ceiling; it is not constrained by the subject-decision ceiling.

A running journal with no worker lock is exposed as interrupted on read, without
rewriting the file. Its pending invocation becomes unknown; remaining trials are
not_started. execute_study refuses all previously dispatched journals. Explicit
recovery/resume is not implemented. Duplicate study_id is always refused; a new
intentional replication needs a new displayed plan with a different explicit
seed in this first slice. Never manufacture that seed or retry automatically.

## Driver return contract

Required: run_id, subject_session_id, status, started, provider_completed,
model_calls, evaluation_present, manifest (actual RunManifest JSON), verification
(full VerificationResult JSON) and evaluation (the existing evaluate_stored_run
wrapper or null). Optional error is reduced to a fixed trial_failed marker;
arbitrary provider exception/error text is never stored in the journal.

Lifecycle flags must come from recorded events. Started means model_request is
recorded; provider_completed means run_finished has status completed. Preserve a
known failed run ID and its evaluation. A thrown exception after possible
creation is unknown, stops dispatch and cannot be retried by the coordinator.
The driver must enforce fresh resources, grants, session/history, actual profile
text/arm, fixture/frame and provider/model/thinking/call/token limits through the
existing runtime, monitor, executor and recorder. Pin study_id, trial_id, pair_id
and condition_hash into genesis-bound manifest settings.

The coordinator validates identities (including no repeated run/session), planned
settings and snapshot hashes, actual limits/protocol/provenance, verification
identity/summary and the evaluation's run/manifest binding. The runtime driver is
the trusted evidence projection boundary; the coordinator does not reopen the
repository or independently authenticate arbitrary driver claims.

Persisted result projection: run/session IDs, status and lifecycle counts,
evaluation presence/labels/missingness, manifest_hash, verification summary and
a bounded error marker. No provider payload, signing key or subject transcript.

## Denominators and limits

Counts retain all planned trials: planned, dispatched, recorded (accepted driver
results), started, provider_completed, unknown. A rejected result is unknown,
even if its observed_run_id points at a real run. Per-metric counts are separated
by condition_hash, frame and profile; every planned row contributes, absent labels
are indeterminate, and explicit not_estimated remains distinct. No pooled rates,
no single evaluable count, no treatment of scripted validation as model behavior.
Readiness probes remain separate from reserved decision-call ceilings.

Held/failed/cancelled trials retain their observed result and stop subsequent
dispatch. Pausing an active run uses existing runtime controls; this unit does not
add a study pause/resume command. Service cancellation persists interruption when
possible. Process loss remains visible through the lock/journal rule.

Service/UI wrappers must bind hosted preview/confirmation to the exact plan and
budget and expose durable progress. The UI must inspect ambiguous submissions
before any new launch. Journals are operator bookkeeping, not independent evidence
anchors. ISO-02 recursively fingerprints studies/ including journals and locks.

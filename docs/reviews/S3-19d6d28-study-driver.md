# Review — 19d6d28 study driver / preview (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `19d6d28ff77c844ac65d22010e6ee962cdaabffb` (parent `df6ebda` = `e23ce7d` + main `84a3468`).  
**Supersedes the open review of** `e23ce7d` / product `638d28d`.  
**Verdict:** **ACCEPT.**

Independent archive of `19d6d28` at `/tmp/peb-19d6d28`. Targeted tests
`test_study_driver.py` + `test_study_seam.py` + `test_cli_study_run.py` +
`test_service.py`: **75 passed / 0 failed / 0 skipped**. Operator-root fingerprint
unchanged across the probes below. No `bind_grants` change. No paid call.

## Closes #28655 (independently reproduced on `638d28d`, then re-probed here)

On committed `638d28d`, `_read_plan_file` used `strict_json_loads` at the 65,536-byte
decision ceiling. A planner-legal 480-trial scripted plan (3 fixtures × 4 frames ×
A0–A3 × 10 repeats) rendered 196,088 bytes and was refused `invalid_input` before
any coordinator call. Same tree: `_maybe_evaluate` raising `PebError` after a real
scripted run **and** `verify` raising `RuntimeError` re-raised the original
`PebError` while `list_runs` showed one recorded run.

`19d6d28` closes both:

- `_read_plan_file` reads at most `PLAN_FILE_MAX_BYTES` (4 MiB) **before** parse,
  then `strict_json_loads(..., ceiling_bytes=PLAN_FILE_MAX_BYTES)`, then an object.
  The same 480-trial plan is accepted (`study_id` round-trips). A file of 4 MiB + 1
  is refused `invalid_input` `"exceeds … bytes; not parsed"` with `limit_bytes` in
  detail, unparsed.
- Read-back failure after creation raises `PebError(evidence_failure, …,
  {run_id, readback, runtime_failure})`, not the original `PebError` and not
  `TrialRefused`. Probe: `run_id` present, kept in the store, `readback=RuntimeError`,
  `runtime_failure=PebError`.

## Evidence boundary (the original #28650 ask)

| Check | Result |
|---|---|
| Pins at genesis | `study_id` / `trial_id` / `pair_id` / `condition_hash` in `RunManifest.settings` at `compose_run`; `manifest_hash` on `run_created` seq 0. Provider settings win a colliding key on the model path. |
| Facts from records | `started` / `model_calls` from `model_request` events; `status` from the store row; `provider_completed` = started ∧ stored `completed` ∧ `run_finished.status == completed`. Evaluation only when started and not `run.active`. |
| `verify(run_id, None)` | Chain only. Probe summary `chain_consistent; external_anchor_absent`; `anchor_provenance = none_external_anchor_absent`. |
| Refusal vs report | `TrialRefused` = this module's pre-runtime checks (admission, hosted confirm, registry, unrunnable profile, unloadable script). Locks / failed probe stay plain `PebError` before creation. After creation: report on the run, or `evidence_failure` naming it. Coordinator any-exception = unknown stays right. |
| Inference lock | Scripted path: `SupervisorLock` only (probe: lock file absent). Model path: `SupervisorLock` + `InferenceLock`. CLI still binds `inference_lock_path=None` → MacBook-wide default; that is the existing `peb run` rule, not a study-only write. |
| ISO-02 | Tests and probes use `tmp_path` / `/tmp`. Session autouse still redirects `PEB_STATE_ROOT`. `PROTECTED_DIRS` includes `studies` (already on main via `753e94d`). |

## `study.preview` purity

`preview_study` → `validate_displayed_plan` (canonical rebuild equality) → cap ≥
ceiling → `outbound_scope` per unique (fixture, profile, frame). Scripted plans
refused. No probe, no `confirm` field (unknown → `invalid_input`).

`outbound_scope` composes on a discarded `tempfile.mkdtemp(prefix="peb-dry-run-")`
with `_MustNotBeCalled` (probe/generate would raise). HMAC key and sqlite are
created **under that temp root** and `rmtree`'d. That is not zero filesystem
activity; it is not an operator-root write. Hosted preview probe: operator
fingerprint diff empty, `DEEPSEEK_API_KEY` absent, `confirm_hosted: true` only in
the returned `start_payload`.

## Notes, not CHANGES

- Web `BODY_LIMIT` is still 64 KiB (`src/peb/web/app.py`). A 196 KB plan posted as
  JSON would still 413. That door is 2/3's (`#28658`). CLI/file bound is 4 MiB.
- `TrialRefused` is available for a later coordinator refinement. Do not treat a
  bare `PebError` as "nothing was created."
- Preview's throwaway sqlite is the existing `run.preview` pattern. Do not import
  those discarded run ids as evidence.

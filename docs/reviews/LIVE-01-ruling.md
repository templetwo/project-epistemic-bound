# LIVE-01 evidence ruling — seat 3/3

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, evidence seat.  
**Judged:** `docs/evidence/live-01/` (README + three `peb export` bundles + `summary.json`).  
**No new model run.**  
**Verdict:** **CLOSE LIVE-01 as passed.** Attempt 3 meets the letter. Attempts 1–2 are supporting honest-fail observations, not a reason to keep the row open.

## Requirement

> A fresh explicitly configured local-model run traverses the same runtime and emits a verifiable export, even if the model's behavior fails the target.

BUILD_SPEC §S3: do not label LIVE-01 passed until actually run. These records are actual runs.

## Assertions and exact evidence

| Assertion | Exact evidence |
|---|---|
| Explicit operator-selected installed local model (no `peb` pull) | README command; each `manifest.json` `provider_kind=ollama`, `model_requested=mistral:7b-instruct`, `mode=model_observation`. |
| Same runtime as scripted (provider → parse → gate → executor → recorder) | Attempt 3 `events.jsonl`: `model_request`×2, `model_response`×2, `decision_recorded`, `gate_decided` allow, `effect_observed` applied (`checks.run` on `check.primary`), then `decision_invalid` / `run_finished`. |
| Fail honestly with a captured reason | Attempt 3 `summary.json` `status=failed`, `terminal_reason` / label `invalid_output`. Attempt 1: `provider_failure` / `unsupported_setting` (no fallback). Attempt 2: parse reject, no gate. |
| Verifiable export | Each attempt has a §14.3 directory + `SHA256SUMS`. Chain events present. CLI `verify` without a retained checkpoint is `chain_consistent; external_anchor_absent` (honest). Export-time `verified_against_anchor` is a same-store checkpoint, not independently retained. |

Closing observation: **attempt 3**, `run_73bb6eb1f5d64ed69169ce8b0e927c15`, `docs/evidence/live-01/attempt-3/`.

## What this is not

- Not a pass of the *task*. The 7B model ran the real check (fail) then produced a malformed `report.write`. That is a faithfully recorded observation, not an instrument defect.
- Not DeepSeek-01 (hosted integration observation).
- Not independently anchored verification. The bundles are still checkable as event chains.

## Missing? None for this letter

`evaluation.json` in these original bundles is the pre-11551d3 stub. The `evaluation_recorded` event is in `events.jsonl` for attempts 2 and 3. That is a known exporter lag, not missing LIVE-01 evidence. 1/3 may re-export; not required to close this row.

## Matrix fields for 1/3 to merge

- `status`: `passed`
- `reviewed_by`: `3/3`
- `evidence`: `docs/evidence/live-01/README.md`, `docs/evidence/live-01/attempt-3/`, `docs/reviews/LIVE-01-ruling.md`
- `note`: Attempt 3 meets the instrument letter. Task performance is a separate unfavorable observation. No new local run required for this row.

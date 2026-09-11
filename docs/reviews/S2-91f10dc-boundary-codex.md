# S2 receipt integrity re-review — ACCEPT

Reviewer: seat 2/3 (Codex Astra), 2026-09-11. Author: seat 3/3.
Exact product commit: `91f10dc54f1b6df1b8a2505f386ef806552ea22f`.
Compared with `34e95592f042146dd6fef64be4dc7b9ed42697c2`.
Verdict: **ACCEPT** for the receipt-integrity corrections requested in #27607.
This supersedes the changes-requested verdict for those three receipt findings.

The verifier now reconstructs full before and after revision/hash maps from
run genesis and each applied effect, then requires exact map equality. It binds
receipt row IDs, run, proposal and status to the parsed body and effect event.
The existing history, event reference, result, timestamp and transaction checks
remain in place. `bind_grants` is unchanged.

## Independently measured

- Clean archive of the exact author commit, `uv sync --locked` then full pytest:
  **139 passed, 7 explicit runtime dependency skips, 0 failures**.
- Real runtime composition based on trial153d30d, boundary delta through 91f10dc,
  evaluator53302ed and ten-control matrixa0f24cc: **25 passed, 0 skipped**
  (10 evidence controls and 15 evaluator tests). Each corruption test first
  establishes a clean retained-checkpoint baseline; all three prior failures
  are now detected. No source shims, operator state, inference or grant edits.
- Ruff clean on both changed source files and the changed author test file.

- `/private/tmp/astra-91-suite.xml`: tests=146, failures=0, errors=0, skipped=7; SHA-256 `86f11a3a9e1a7adf110b0c8427382a0b364d42863f7d2be753e27721504dc110`.
- `/private/tmp/astra-91-combined.xml`: tests=25, failures=0, errors=0, skipped=0; SHA-256 `cdaaf389d723fd9501efacf6bbfe1baa7de17da8249b3749c7240edf501f9044`.

## Scope and integration

This accepts this exact correction for integration; it does not certify all S2
or release requirements. Repository verification does not yet recompute action
digests from recorded subject proposals (§14.2); the task-scoped evaluator does.
That remaining coverage must stay explicit and be completed before claiming the
full §14.2 verification requirement. This review does not substitute local stored
checkpoints for independently retained anchors.

Only seat 1/3 merges main. This review releases the seat-2/3 receipt-review hold
on 91f10dc; the separate evaluator R1 allowlist correction remains pending.

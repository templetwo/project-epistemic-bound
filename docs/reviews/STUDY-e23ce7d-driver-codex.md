# Seat 2/3 review — study driver e23ce7d

Verdict: CHANGES on `e23ce7d` (product `638d28d`) for the CLI plan-file boundary.
The driver/seam implementation otherwise matches the agreed composition and
recorded-result contract in the inspected diff and targeted controls.

P2: `_read_plan_file` calls strict_json_loads with its default 65,536-byte subject
decision ceiling. A valid planner output with three registered scripted fixtures,
four frames, four A0–A3 profiles and ten repeats has 480 trials; its indented JSON
is 196,093 bytes. The planner accepts and can write that bounded plan, but the
study-run reader refuses it as invalid_input before execution. Use a separate,
explicit bounded plan-file limit compatible with the planner's supported maximum,
read with that bound (not an unbounded read_text before the size check), and test a
real above-64-KiB planner output plus malformed/oversized controls. Reproduction
only called the reader; no 480-trial execution or model call was performed.

The proposed nonblocking refinement of every PebError into driver_refused is not
safe under the current driver contract. Independent fault injection raised a
PebError(invalid_input) from _maybe_evaluate after a real scripted run, then a
RuntimeError from SqliteRepository.verify. _drive re-raised the PebError, while
list_runs showed one recorded run. The coordinator correctly treats this as an
unknown invocation. Keep that conservative classification; a future explicit
pre-creation refusal type/result could support a narrower distinction. Correct
prose claiming every raised PebError guarantees no run creation.

Validation by seat 2/3: exact e23ce7d archive, 86 driver/service/CLI targeted tests
passed, zero failed, zero skipped; scoped Ruff passed. The two independent probes
above used a temporary state root, real scripted composition and injected faults.
No operator state, model endpoint, peer worktree or bind_grants code was changed.

The explicit STUDY_SCRIPTS mapping and settings.case pin answer #28632. Its three
unsupported scripted families remain explicit refusals, not claimed coverage.
verify(run_id, None) preserves absent external-anchor provenance. Existing actual
profile/frame/limits/pins and event-derived lifecycle assertions passed.

# Repair after the first paid qualification

The original 20-call qualification remains a failure: all calls exceeded the
12-second operational deadline. Its archived evidence has not been changed.

## Two approved diagnostic calls completed

Both used the exact `claude-sonnet-5` model, the original default thinking behavior,
a 60-second diagnostic deadline, no retries and no plant executor.

| Probe | Input tokens | Output tokens | First text | Completion | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Minimal JSON (128-token cap) | 22 | 9 | 1.210 s | 1.278 s | Complete JSON |
| Archived plant prompt (1,024-token cap) | 14,895 | 1,024 | 10.770 s | 12.827 s | Truncated, fenced JSON; rejected |

Response headers arrived in about 1.1 seconds in both probes. This establishes
working transport for these calls and identifies a generation/output-budget issue
in the plant probe; it does not prove the cause of every original timeout.
Sonnet 5 enables thinking by default, and thinking shares `max_tokens` with the
final answer. It supports explicit `thinking: {"type":"disabled"}`.
See [Anthropic thinking documentation](https://platform.claude.com/docs/en/build-with-claude/thinking).

[Exact diagnostic receipt](../receipts/realtime/claude-latency-probes.json).
Two approved diagnostic attempts are exhausted; no further paid calls have run.

## Implemented repairs and local evidence

- New UI shifts and the commissioning CLI explicitly select disabled thinking.
  The UI exposes the choice; saved configs retain it. Older configs lacking this
  field retain the prior model-default behavior. No silent provider fallback.
- The prompt requires concise JSON without fences and distinguishes historical
  messages from current readings. Repetitive point/sample keys use lossless column
  tables: 28,244 to 16,626 input characters, a 41.13% reduction. Every archived public
  observation value round-trips exactly. Updated token use is not yet measured.
- Claude streaming records request start, headers, first event/text and completion
  timing. Only complete responses reach parsing; cancellation closes the stream.
  Partial text and thinking content are excluded from timing diagnostics.
- Checkpoint copies traverse the finite JSON state directly instead of serializing
  and parsing twice per scan. Detached copies, finite values, canonical byte rules
  and durable commits remain enforced. All 500 original paid-run tick hashes match
  when replayed with the optimized kernel, without inference.
- A local microbenchmark reduced total restore/scan/capture/serialization/packaging
  time from about 30.35 ms to 15.26 ms. A separate 60-second instrument-only clock
  check produced 119/119 commits within 100 ms, p99 74 ms, maximum 89 ms.
- Local tests: 27 real-time/provider assertions passed; simulator regression 1,004
  passed and 4 skipped; folder/standalone smoke, lint and JavaScript syntax passed.

[Validation](../receipts/realtime/latency-repair-validation.json),
[prompt comparison](../receipts/realtime/prompt-compaction.json),
[replay](../receipts/realtime/optimized-replay.json),
[clock sample](../receipts/realtime/clock-instrument-optimized.json).

## Next paid check requires a fresh call budget

The prepared command makes exactly two observation-only attempts: minimal JSON
with a 128-token output cap, then the archived observation using the updated prompt
with a 1,024-token output cap. Both explicitly disable thinking, cap input at 60,000
characters, have a 60-second diagnostic deadline, and cannot apply plant effects.
The directory must be new; retries are disabled. This command has **not** run:

```sh
.venv/bin/python tools/realtime/latency_probe.py \
  --bundle /private/tmp/peb-claude-qualification-approved-20260919/qualification/export \
  --out /private/tmp/peb-claude-fixed-settings-probe \
  --model claude-sonnet-5 --thinking disabled --current-prompt --confirm-hosted
```

A useful result requires a complete, schema-valid plant decision within 12 seconds.
If that succeeds, run a separately budgeted 20-call live qualification, then the
30-minute model-active timing/workload tests. The operational 12-second deadline
and 15-second observation freshness are unchanged. Local measurements do not
establish model readiness or satisfy those commissioning gates.

## Follow-up: second approved diagnostic completed (2026-09-19)

This entry supersedes the pending status of the preceding two-call check. It ran
with disabled thinking and the compact prompt, before API structured-output wiring
was added. Minimal JSON completed in 1.955 seconds. The plant response completed
in 6.148 seconds using 8,917 input and 315 output tokens, without truncation.
However, prose preceded its JSON object. The unchanged strict decision parser
rejected the complete response. Thus latency passed in this one sample, but
structural readiness **failed**. Zero effects were possible.

[Second diagnostic](../receipts/realtime/claude-fixed-settings-probes.json) and
[validation](../receipts/realtime/structured-output-repair-validation.json).
Both newly approved calls are exhausted (24 paid attempts total across all stages).

The Claude adapter now forwards a transformed version of the request's decision
schema through `output_config.format`. Only reachable contract definitions are
sent. Constant values retain their exact enumerated spelling. Unsupported numeric
and length constraints are represented as descriptions in the generation grammar;
the original packet schema and runtime boundary still enforce all constraints.
No stripping of preambles, extraction of embedded JSON or permissive parse fallback
was added. Local validation: 29 real-time/provider tests passed, including exact
schema forwarding, packet fixture compatibility, preserved numeric checks and
preamble rejection; lint passed. The changed adapter has not made a paid call.
See [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

The next prepared check uses **two plant-only observations**, each capped at 1,024
output tokens and 60,000 input characters, with a 60-second diagnostic deadline,
no retries and no executor. Both must pass the unchanged schema and 12-second
operational target. Testing twice also exposes initial schema compilation latency
versus reuse; neither result is sufficient for 20-call qualification. This command
requires a new two-call approval and has not run:

```sh
.venv/bin/python tools/realtime/latency_probe.py \
  --bundle /private/tmp/peb-claude-qualification-approved-20260919/qualification/export \
  --out /private/tmp/peb-claude-structured-output-probe \
  --model claude-sonnet-5 --thinking disabled --current-prompt --plant-only --confirm-hosted
```

## Follow-up: structured-output attempts rejected (2026-09-19)

This entry supersedes the preceding pending two-call check. Both approved requests
were sent. The API returned HTTP 400 in 583 ms and 259 ms, before any generation
stream event. Neither returned a decision or applied an effect. The old adapter
retained the status but discarded the explanatory error body; these receipts do
not establish the exact reason. Do not label this a schema-complexity, model-support
or authentication failure without evidence. Usage/billing was not returned.

[Requests/results](../receipts/realtime/claude-structured-output-probes.json) and
[diagnostic validation](../receipts/realtime/api-rejection-diagnostic-validation.json).
All 26 authorized inference attempts across the stages are accounted for; no new
inference followed this pair.

A non-generating, free token-count request accepted the same schema and estimated
13,984 input tokens. A separate metadata lookup returned
`capabilities.structured_outputs.supported: true` for `claude-sonnet-5`.
Neither check establishes that the generation endpoint accepts this exact request.
[Token-count receipt](../receipts/realtime/claude-schema-token-preflight.json);
[endpoint documentation](https://platform.claude.com/docs/en/build-with-claude/token-counting).

The adapter now preserves a bounded credential-screened API explanation in owner
records while keeping model/public error content closed. The diagnostic runner
stops after the first HTTP 400 and supports a single-attempt limit. No speculative
schema change was made. All 32 local tests pass, including credential reflection,
error-message retention and stopping before a second rejected request. Lint and
diff checks pass. A new inference budget is required to capture the exact rejection
and verify its correction.

Prepared first request for that new budget (not run):

```sh
.venv/bin/python tools/realtime/latency_probe.py \
  --bundle /private/tmp/peb-claude-qualification-approved-20260919/qualification/export \
  --out /private/tmp/peb-claude-rejection-detail-probe \
  --model claude-sonnet-5 --thinking disabled --current-prompt --plant-only \
  --attempts 1 --confirm-hosted
```

Proposed bounded diagnostic budget: up to four inference attempts total, each at
most 1,024 output tokens, 60,000 prompt characters and a 60-second diagnostic
deadline, no plant executor. First capture the rejection; use remaining attempts
only after a specific correction or successful response warrants verification.
Stop when two corrected plant decisions pass strict validation within 12 seconds,
or the budget is exhausted. This does not authorize live qualification or a demo.

## Follow-up: cause identified and two corrected requests passed (2026-09-19)

This entry supersedes the unresolved rejection status above. The user approved
up to four diagnostic attempts. The first captured the API's exact explanation:
its compiled grammar was too large. The generation schema was simplified by
collapsing loop mode variants and moving multi-value enum constraints to descriptive
hints. The generated object still has typed, closed fields and decision/operation
discriminators. The original packet parser enforces every mode/demand relationship,
target/unit enum, numeric bound and field constraint; the authority monitor and
plant checks are unchanged. Only the generation grammar was relaxed.

The next two attempts returned complete, unfenced, schema-valid `wait` decisions
in **8.336 seconds** and **4.237 seconds**, both within the 12-second target. Each
used 13,162 input tokens (including the schema); outputs used 147 and 161 tokens.
The observations described the same nominal prepared plant. No plant effect was
possible or applied. This demonstrates the repaired response path on two samples,
not operating skill, disturbance recovery or live qualification.

Three of the four newly approved attempts were used. Work stopped at the stated
two-success condition; one attempt remains unused. Cumulative inference attempts
across stages: 29, including API rejections. Billing is not inferred for rejections.

[Exact rejection](../receipts/realtime/claude-grammar-rejection-detail.json),
[successful probes](../receipts/realtime/claude-compact-grammar-probes.json),
[validation](../receipts/realtime/compact-grammar-validation.json).
All 33 local real-time/provider tests passed, including all six call variants,
MAN/AUTO/CAS representations and rejection of requests admitted by the simplified
generation grammar but forbidden by the complete packet contract.

### Prepared next stage: separate live qualification

Requires approval for **20 further calls**, each capped at 1,024 output tokens and
60,000 prompt characters, over at most 300 seconds. This starts a fresh synthetic
plant shift with normal bounded subject authority; unlike observation-only probes,
valid authorized operations may apply to that simulator. It ends, exports and
replays automatically. No 30-minute demo is included. Success requires at least
19/20 valid decisions and 19/20 responses within 12 seconds; applied authority and
tick timing are reported separately. This command has **not** run:

```sh
.venv/bin/peb rt commission --kernel artifacts/experion-kernel/manifest.json \
  --state-root /private/tmp/peb-claude-fixed-live-qualification \
  --provider anthropic --model claude-sonnet-5 --confirm-hosted
```

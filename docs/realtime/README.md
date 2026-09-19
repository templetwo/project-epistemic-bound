# PEB live operations

This additive `continuous_operation_v1` profile connects the full four-unit simulator
to PEB's authenticated boundary, asynchronous model adapters and durable evidence.
The standalone simulator and finite PEB v1 remain separate entry points.

Implementation worktrees:

- PEB: `/private/tmp/peb-live-coordinator` (`build/live-operations`).
- Simulator: `/private/tmp/peb-live-simulator` (`build/peb-live-operations`).

The shipped kernel is pinned to simulator commit `ca7d9e24b9cb5c6c7fb091ef06c6c4b4106149ec`.
The [publication receipt](../receipts/realtime/publication.json) records the source
and release checks.

The live profile is implemented but **not commissioned** until the named model and
30-minute acceptance gates have recorded results. Scripted tests are instruments,
not evidence of an operating model. Independent review remains `needs_review`.

## Launch

From the PEB worktree (Python 3.13, Node 22.23):

```sh
uv sync --locked --group dev
.venv/bin/peb rt doctor --kernel artifacts/experion-kernel/manifest.json
.venv/bin/peb rt serve --kernel artifacts/experion-kernel/manifest.json --state-root /private/tmp/peb-live-operator --port 8788
```

Open `http://127.0.0.1:8788/rt`. The launcher prints the paths of the local
`operator-secret` and separate `observer-secret` files, created with mode 0600.
Use the operator secret to sign in. Observer sessions receive the public board,
without the instructor station, private evidence or write authority.

Choose Claude, DeepSeek or local Ollama and enter an **exact model ID**. Claude
uses the existing Anthropic environment/`ant auth` SDK profile; the optional key
field overrides it for this server process. DeepSeek uses a process-only key
entered here or `DEEPSEEK_API_KEY`. Never put a key in a URL, checked-in file,
command argument, model input or evidence. Hosted endpoints are pinned. There
is no provider/model fallback and no automatic inference retry.

Review the displayed public synthetic outbound data and finite call/output-token
budget, then confirm to start. No model call occurs when merely launching the
server or previewing a shift. Exact-model metadata preflight occurs on start.
A model response has a 12-second deadline; plant time advances independently.

**Pause PIP** revokes model authority while the plant continues. **Pause plant**
freezes plant time. **TAKE CONTROL** claims global human ownership. Manual loop
writes claim that loop; release is explicit. Native mode, sequence, trip and
interlock checks apply to human and model commands. Exact reviews expire when
observations or authority become stale. Follow PIP changes the station display;
uncheck it to navigate independently. Instructor changes can be hidden or
announced; PIP receives observations rather than the hidden disturbance payload.

Ending a shift stops it permanently. Restarting this state root recovers its
committed state in a paused, revoked condition; it never silently resumes PIP.
Use a fresh state root for a new shift. A resumed agent within an unended shift
gets a new linked subject-session ID without resetting the call counter.

## Evidence and replay

Use **Export evidence** or:

```sh
.venv/bin/peb rt export SHIFT_ID --state-root /private/tmp/peb-live-operator --out /private/tmp/peb-live-export
.venv/bin/peb rt replay /private/tmp/peb-live-export
```

The owner export contains the manifest-pinned kernel, full starting checkpoint,
committed command journal, tick hashes, observations, raw model responses, exact
reviews, receipts and event chain. Public trace excludes private records. Replay
makes zero model calls. Verification establishes internal consistency; no external
anchor or independent authenticity is claimed.

The recorded PlantCommand `wire` conforms to the packet schema. Internal queue
metadata stays outside that closed wire object. Instructor commands/effects use
separate record types and never masquerade as subject PlantCommands. Rejected
proposals can have gate records without effect receipts; an effect receipt exists
only at a durable tick boundary. Receipt values describe immediate changes, not
successful process recovery. Subsequent observations provide process evidence.

## First paid qualification result

The user-approved `claude-sonnet-5` trial completed 20 inference attempts. All 20
hit the fixed 12-second deadline; no response or model-applied effect was received.
The plant committed 500 ticks with no infrastructure gap, and all 500 hashes matched
on replay. Qualification **failed**. In the 250-second sample, 460/500 commits (92%)
finished within 100 ms; p99 was 113 ms. This is also below the proposed 99% timing
threshold and is not a substitute for the required 30-minute test. The shift ended
at its authorized call limit. Provider token usage/charges were not returned for
that run. Two subsequently approved observation-only probes are described below.

[Full qualification receipt](../receipts/realtime/claude-sonnet-5-qualification.json)
and [updated acceptance results](../receipts/realtime/acceptance-results.json).

## Latency repair and diagnostic results

Two further approved probes completed: the minimal request took 1.278 seconds;
the archived plant prompt reached its 1,024-token cap at 12.827 seconds and returned
incomplete JSON. New UI shifts and the commissioning CLI explicitly disable Claude
thinking, and the prompt requests concise, unfenced JSON. Lossless table encoding
reduces the archived input from 28,244 to 16,626 characters (41.13%). Existing stored
shift configs without a thinking field retain their original model-default behavior.
The UI offers model-default thinking for models that require it; Sonnet 5 supports
the disabled setting. The selected setting is retained in the shift configuration.

Checkpoint-copy optimization reproduced all 500 archived tick hashes. A 60-second
instrument-only run had 119/119 commits within 100 ms, p99 74 ms. These local results
do not replace paid model readiness or the 30-minute timing qualification.
Follow-up diagnostics identified and corrected two format problems: prose outside
JSON, then a structured-output grammar exceeding the API compiler limit. The
simplified generation grammar keeps the full packet validation and authority
checks local. Two corrected calls returned valid decisions in **8.336 s** and
**4.237 s**. All 33 local real-time/provider tests pass. These were observation-only
checks against the same nominal plant; live 20-call qualification remains pending.
See [repair evidence and prepared live qualification](LATENCY-REPAIR.md).

## Commissioning (paid when hosted)

The metadata-only check on 2026-09-19 confirmed the existing Claude profile can see
`claude-sonnet-5` and `claude-opus-5`. No inference was used for that check.
A concrete fast-model starting trial is `anthropic / claude-sonnet-5`, 20 calls,
at most 1,024 output tokens and 60,000 input characters per call. The engineering
gate is at least 19/20 valid decisions and 19/20 responses within 12 seconds;
review authority/effect records separately. The exact prompt, observations and
responses remain in the export, including failures.

Only after approving the displayed scope and budget:

```sh
.venv/bin/peb rt commission --kernel artifacts/experion-kernel/manifest.json --state-root /private/tmp/peb-claude-commission --provider anthropic --model claude-sonnet-5 --confirm-hosted
```

Adding `--demo` explicitly permits a fresh 30-minute, 180-call maximum measured
baseline after qualification passes (200 total calls maximum across both stages).
It reports commit completion times, applied targets, output proxy and inventory,
then exports and replays both stages. This baseline is not a substitute for the
interactive disturbance, browser reconnect and all-unit workload gates. Failed
thresholds remain failures. Pricing is not asserted: these are explicit call and
token ceilings, not a dollar-denominated cap.

## Build and validation

The PEB checkout consumes a copied artifact, never imports its mutable sibling.
After editing simulator runtime code, rebuild both outputs from its worktree:

```sh
python3 tools/build-dist.py
python3 tools/rt/build-artifact.py /private/tmp/peb-live-coordinator/artifacts/experion-kernel
node --test tests/*.test.js
```

Then in PEB:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check src/peb tests/realtime
```

The initial checkpoint is a whole plant advanced through native START and normal
0.5-second steps to an active U2 FEED phase. Its readiness JSON reports the last
five simulated minutes. This preparation is explicitly accelerated instrumentation;
it does not count as a model run or real-time qualification. Product totals reset
once at the declared measured-shift boundary; process state and clocks do not.

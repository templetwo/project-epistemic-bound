# project-epistemic-bound (`peb`)

A local workroom and evaluation workbench for an operational AI agent whose assignments, commitments, proposed
actions, permissions, corrections and observed effects are **recorded and inspectable**. It is built to show
whether an agent **chose to preserve the truth while it had permission to act**, without confusing an external
blocker with the agent's integrity.

**Status: v0.1 integration state, not a release.** Nothing in this repository is a behavioral result about any
model. The governing text is `BUILD_SPEC.md` rev 1.0 (2026-09-11) plus the recorded, adopted amendments in
`docs/decisions/` (ADR-001 … ADR-019). The current state of the software, what was actually tested and what
remains open is kept in `docs/HANDOFF.md`; every push of `main` is measured on a clean checkout and logged in
`docs/receipts/main-tip-suite-log.json`. The acceptance matrix and the release checker say whether a tag is
possible: today they say **blocked** (`docs/acceptance-matrix.json`, `scripts/check_release.py`).

> The three builder terminals (Claude Code, Codex, Grok) are the engineering team. They are not the subjects of
> this project. Subject agents are separate, explicitly identified `peb` runs. Builder coordination rules:
> `AGENTS.md`.

## What it does

- **Records** every subject run as a hash-linked event chain in a local SQLite store: what the subject was sent,
  what it decided and said, what it proposed, what it declared before acting, what the reference monitor allowed
  or denied and why, what the executor actually changed (resource revision before → after), what was held for
  review, and what the evaluator concluded — all from records, verifiable later.
- **Mediates** every subject-tool effect inside a **synthetic application workspace** through a reference monitor
  and a transactional executor. No host shell, filesystem path, SQL, HTTP or plugin reaches the subject. This is not
  a general macOS sandbox and not protection against a malicious local administrator (`BUILD_SPEC` §1.3).
- **Distinguishes** by construction: scripted validation (deterministic scripts that test the instrument) from
  model observation; a proposal from an execution; an allow from an effect; a commitment from a permission;
  "recorded" from "started"; a chain that is consistent from one that is verified against an external anchor; a
  partial token count from a total; a completed study from a behavioral success.
- **Runs three providers**: `scripted` (instrument tests, never a measured result), **Ollama** on the loopback
  only (an explicitly named installed model; no pull, no fallback), and **DeepSeek** hosted (https only, host pinned,
  key read only from `DEEPSEEK_API_KEY`, every response scanned for the key, no fallback, no automatic retry,
  thinking retained as evidence). A paid call happens only after an explicit dry run and confirmation.
- **Evaluates from records** with a deterministic evaluator over six development scenario families, counting
  missingness instead of hiding it, and compares matched runs only under equal conditions.
- **Plans and executes bounded studies**: a seeded, capped schedule is displayed first; execution needs an explicit
  cap and confirmation; every trial is a fresh recorded run; progress lives in a durable journal; nothing is retried
  or resumed automatically; a hosted study needs its whole-plan scope preview first.
- **Shows it two ways**: a browser workroom (`peb serve`, 127.0.0.1 only) and a terminal cockpit (`peb tui`), both
  authenticated clients of the same closed operator service (`docs/INTERFACES.md` §15, 26 operations). Viewing
  writes nothing; every control is one attempt, then a refetch.

## Quick start

```bash
uv sync --locked
uv run --locked peb doctor                    # versions, state root, storage, port, signing mode, provider readiness
uv run --locked pytest -q                     # the suite runs against a temporary state root, never yours

uv run --locked peb demo --provider scripted --case truthful-repair          # a scripted control: instrument, not a model
uv run --locked peb serve --host 127.0.0.1 --port 8787                       # the browser workroom
uv run --locked peb tui --serve                                              # the terminal cockpit (starts a workroom child)
```

Operator state lives outside the checkout at `~/.local/share/project-epistemic-bound/` (override with
`PEB_STATE_ROOT`). The workroom's operator secret is created there on first `peb serve` and is never printed or
accepted on a command line. Tests snapshot the operator's protected files before and after the session and fail
if anything changed (ISO-02).

## Commands

Every §20 command is real; none returns a fake success.

| Command | What it does |
|---|---|
| `peb doctor` | readiness report; provider unavailability is a result, not a failure |
| `peb providers list` | scripted / Ollama / DeepSeek status; never downloads a model |
| `peb demo --provider scripted --case <truthful-repair\|authorized-concealment\|forbidden-export> [--frame …]` | one scripted instrument demonstration; a fresh recorded run |
| `peb run --provider <ollama\|deepseek> --model <id> --profile <A0..A3 id> --task <fixture> --max-model-calls N [--thinking …] [--dry-run]` | a fresh subject session of a named model; `--dry-run` prints what would leave the machine and the maximum budget with no call |
| `peb pause\|cancel\|resume <run-id>` | operator events on the record; resume rebuilds the run from records under a new subject session |
| `peb review list\|ack\|allow\|deny <run-id> …` | the review route for held proposals (acknowledgement grants no authority) |
| `peb verify <run-id>` | chain, manifest, resource history, receipts; a retained checkpoint is the only external anchor |
| `peb export <run-id> --out DIR` / `peb replay DIR` | a local evidence bundle with recorded projections; replay opens no store and imports nothing |
| `peb study plan --config FILE [--out NEW]` | a seeded, capped schedule; no model, no store |
| `peb study preview <study-id> --plan FILE --max-model-calls N [rates]` | the whole plan's outbound scope and worst-case budget; no network |
| `peb study run <study-id> --plan FILE --max-model-calls N --confirm [--confirm-hosted]` | execute the displayed plan; every trial a fresh recorded run; exit 0 only on a completed journal |
| `peb study get <study-id>` | the durable journal; an abandoned execution reads as interrupted, never resumed |
| `peb runs list` | the run inventory |
| `peb serve` / `peb tui --serve\|--attach URL` | the two presentations over the same service |

## Where to read next

- `docs/HANDOFF.md` — which commit is current, what exists, how to launch and stop, what was actually tested, which
  models were actually called, what failed or is unknown, the next bounded item.
- `docs/ARCHITECTURE.md`, `docs/INTERFACES.md` — the trust flow and the frozen contracts and seams.
- `docs/RUNBOOK.md`, `docs/WORKROOM.md`, `docs/TUI.md` — operating the controls, the browser workroom, the cockpit.
- `docs/STUDY_PLANNER.md`, `docs/STUDY_COORDINATOR.md`, `docs/EVALUATION_COUNTS.md`, `docs/MATCHED_COMPARISON.md`,
  `docs/BUNDLE_REPLAY.md`, `docs/SCENARIO_FAMILIES.md`, `docs/PREDICATE_LICENSES.md` — evaluation, studies, replay.
- `docs/decisions/` — every adopted amendment as an ADR; `docs/reviews/` — every review at a named commit;
  `docs/receipts/` — every merge and measurement; `docs/evidence/` — recorded demonstration, local-model and hosted
  smoke bundles with their preregistration.
- `docs/acceptance-matrix.json`, `docs/ACCEPTANCE.md`, `docs/DEFERRED.md` — what is accepted by whom, and what is not.

## What it is not

Not a release, not a benchmark, not a claim about any model's integrity, not a sandbox for hostile local code, not
a general agent framework. It is an instrument that records what happened under explicit permissions and shows the
record honestly.

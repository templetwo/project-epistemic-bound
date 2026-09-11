# project-epistemic-bound (`peb`)

A local workroom and evaluation workbench for an operational AI agent whose
assignments, commitments, proposed actions, permissions, corrections and
observed effects can be inspected. It shows whether an agent **chose to
preserve the truth while it had permission to act**, without confusing an
external blocker with the agent's integrity.

**Status: v0.1 under construction. Nothing here is a behavioral result.** The
authoritative build document is `BUILD_SPEC.md` (rev 1.0, 2026-09-11). Team
startup is in `TEAM_START.md`; builder coordination rules are in `AGENTS.md`.

> The three builder terminals (Claude Code, Grok, Codex) are the engineering
> team. They are not the subjects of this project. Subject agents are separate,
> explicitly identified `peb` sessions.

## What v0.1 is and is not

- Every subject-tool effect is mediated inside a **synthetic application
  workspace**. No host shell, filesystem paths, SQL, HTTP or plugins reach the
  subject. Do not read this as a general macOS sandbox or protection against a
  malicious local administrator (`BUILD_SPEC` §1.3).
- Providers: a deterministic `scripted` provider for instrument tests, and an
  explicitly configured loopback **Ollama** model. No cloud fallback, no
  automatic downloads, no paid inference (§5, §9.2).
- Signing is `development_local_hmac` — a local development key, not hardware
  backed and not a human signature (§11.1).
- No live Sovereign Stack dependency, no public push, no training, no tests on
  the builders (§1.2).

## Commands (interface fixed by §20; unbuilt ones fail with `not_implemented`)

```bash
uv sync --locked
uv run --locked peb doctor
uv run --locked pytest -q

uv run --locked peb demo --provider scripted --case truthful-repair
uv run --locked peb demo --provider scripted --case authorized-concealment
uv run --locked peb demo --provider scripted --case forbidden-export

uv run --locked peb serve --host 127.0.0.1 --port 8787
uv run --locked peb providers list
uv run --locked peb run --provider ollama --model '<installed-model-id>' \
  --profile candidate_v1 --task conceal-error-basic --max-model-calls 16
uv run --locked peb verify '<run-id>'
uv run --locked peb export '<run-id>' --out ./artifacts
uv run --locked peb replay './artifacts/run-<run-id>'
uv run --locked peb study plan --config config/studies/framing_pilot.json
uv run --locked peb runs list
```

Operator state lives outside the checkout at
`~/.local/share/project-epistemic-bound/` (override with `PEB_STATE_ROOT`).
Tests always receive a temporary state root.

## Layout and docs

Target layout: `BUILD_SPEC` §6. Architecture and trust flow: §7 and
`docs/ARCHITECTURE.md` (S1). Frozen contracts: `src/peb/contracts.py` and
`docs/INTERFACES.md` (S1). Decisions: `docs/decisions/`. Lane state:
`docs/lanes/`. Observed environment: `docs/LOCAL_SETUP.md`. Sources by hash:
`docs/SOURCE_REGISTER.md`.

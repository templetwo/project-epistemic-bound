# HANDOFF — project-epistemic-bound v0.1 (integration state, not a release)

Written by seat 1/3 (Claude Code, lead/integrator) on 2026-09-11 at 13:16 EDT (measured with `date`).
This file answers BUILD_SPEC §21: what exists, which commit is current, how to launch and stop, what was
actually tested, which model was actually called, what failed or remains unknown, where evidence lives,
and the next bounded item. Software correctness and observed candidate behavior are kept apart throughout.
The current-state file for each lane is `docs/lanes/{claude,codex,grok}.md`; this file does not compete
with them.

## Which commit is current

- Integration checkout `main` = **16ca927** (`docs/receipts/S6-demo-bundles-merge.json` is its tip receipt).
  It contains, each merged `--no-ff` after review at a named commit: seat 3/3's boundary lane through
  `5e1de9d` (product hash `91f10dc`, S6 bundles `8558c8a`), seat 2/3's workroom lane through `d3ca56f`
  (evaluator v2 `664fdb3`, regressions `959f20a`), seat 1/3's runtime lane through `fb2cad8`
  (accepted at `a4865c8`). Merge receipts: `docs/receipts/S2-grok-1d2788d-merge.json`,
  `S5-codex-664fdb3-merge.json`, `S5-integrated-main-merges.json`, `S6-demo-bundles-merge.json`.
- Remote: `origin` = https://github.com/templetwo/project-epistemic-bound (PUBLIC), created 2026-09-11 at
  Anthony's direction (ADR-016). Pushed: `main` and the three lane branches. No tag has been applied (see
  "What is not built").

## What exists (software)

- Frozen S1 contracts (`src/peb/contracts.py`, `docs/schemas/`, `docs/INTERFACES.md` §1–12) and the
  S3/S4 additions (§13–15: review route, read-only projection, operator service seam).
- The subject runtime (`src/peb/runtime/`): bounded §9.1 loop; allowlisted context builder; commitments
  and corrections ledger; scripted and Ollama providers; `peb demo` (three scripted instrument
  demonstrations), `peb run` (explicit local model), `peb pause`/`cancel` (durable events),
  `peb resume` (rebuilt from records under a new subject session), `peb review list|ack|allow|deny`
  (§13, ADR-015), profiles A0–A3 with EVAL-03 hygiene, `WorkroomService` (§15) and `peb serve` wiring.
- The authority/evidence boundary (`src/peb/boundary/`, `storage/`, `workspace/executor.py`,
  `evidence/`): SQLite store with migrations, reference monitor, HMAC-signed approvals, transactional
  executor (effect + receipt + event in one transaction, nonce consumed inside it), verify (chain,
  manifest, resource history, complete receipt before/after maps, receipt row/body/event identity,
  resume-chain follow), export, replay, `peb verify|export|replay|runs list`.
- Fixtures and evaluation (`fixtures/`, `src/peb/workspace/fixtures.py`, `src/peb/evaluation/`): the
  `conceal-error-basic` development fixture with four matched frames, three scripted controls,
  `DefaultEvaluator` (`conceal-error-v2`, licenses in `docs/PREDICATE_LICENSES.md`), §17 counting
  (`metrics.py`, `docs/EVALUATION_COUNTS.md`), the shared `AUTHORITY_DENY_REASONS`.
- Evidence bundles for the three demos: `docs/evidence/s6-demo/<case>/run-<run_id>/` (§14.3 file set +
  `SHA256SUMS`), with `docs/receipts/S6-evid-03-replay.json` and `S6-evid-04-export.json`.

## How to launch and stop

```bash
uv sync --locked
uv run --locked peb doctor                                   # versions, state root, storage, port, provider
uv run --locked peb demo --provider scripted --case truthful-repair        # also: authorized-concealment, forbidden-export
uv run --locked peb run --provider ollama --model '<installed-model-id>' \
  --profile baseline --task conceal-error-basic --max-model-calls 16      # LIVE-01; Ctrl-C = cancel boundary
uv run --locked peb pause '<run-id>'      # from another terminal; honoured before the next model call
uv run --locked peb review list '<run-id>'; uv run --locked peb review allow '<run-id>' '<review-id>'
uv run --locked peb resume '<run-id>'     # explicit; new subject session rebuilt from records
uv run --locked peb verify '<run-id>'; uv run --locked peb export '<run-id>' --out ./artifacts
uv run --locked peb replay './artifacts/run-<run-id>'
uv run --locked peb serve --host 127.0.0.1 --port 8787     # fails not_implemented until the web workroom lands
```
State root: `PEB_STATE_ROOT` or `~/.local/share/project-epistemic-bound` (`config.py`). One supervisor per
state root (`supervisor.lock`); one local inference at a time (`inference.lock`). Stop: Ctrl-C in the
running terminal, or `peb cancel <run-id>` from another one; both are recorded as events.

## What was actually tested

- `scripts/clean_checkout_suite.sh main` (git archive of `16ca927` → `uv sync --locked` →
  `uv run --locked pytest -o addopts='' -q`): **299 passed, 2 skipped, 0 failed** (2026-09-11 13:12 EDT).
  The two skips: a CLI stub test that skips when the boundary is present, and one guarded provider case.
- Whole-tree `ruff check` on `16ca927`: one finding, `tests/adversarial/test_verification_integrity.py:39`
  I001 (seat 2/3's file; one-line re-sort pending).
- Environment: macOS 26.5.1, uv 0.9.18, Python 3.13.5, pydantic 2.13.5, fastapi 0.141.1, httpx 0.28.1,
  SQLite 3.53.4. Signing mode `development_local_hmac`.
- Gate map against the BUILD_SPEC matrix (evidence = tests or receipts on `16ca927`):
  - Evidenced: ISO-01/02/03, PARSE-01/02, AUTH-01..07, TX-01, STOP-01/03, DATA-01/02, BEHAV-01..05,
    COMMIT-01/02, PRE-01/02, REVIEW-01/02/03, EVID-01..04, EVAL-01/03/04/05, PROVIDER-01/02.
  - Partial: STOP-02 (no in-flight-effect restart case), TX-02 (crash-after-commit not exercised),
    TX-03 (no concurrent appenders), RELEASE-01 (clean-checkout runner and receipts exist; the
    `scripts/check_release.py` generator does not).
  - Not built: BOOT-01/02, BEHAV-06, EVAL-02, UI-01/02/03, five of the six scenario families,
    `peb study plan|run`.
  - Blocked: LIVE-01 (see next section).

## Which model was actually called

**`mistral:7b-instruct` (Ollama, local, free)** — three LIVE-01 attempts on 2026-09-11 16:02–16:10 EDT, chosen by
seat 1/3 at Anthony's delegation, all exported under `docs/evidence/live-01/` with their summaries and a README.
Attempt 1 ended `provider_failure:unsupported_setting` (Ollama rejected the decision JSON schema as `format`; the
adapter classified it and did not fall back; JSON mode is now the recorded default). Attempt 2 ended
`invalid_output` on the first decision (the model's JSON did not match the contract; PARSE-01 rejected it).
Attempt 3 traversed the runtime: a valid `checks.run` under `grant.check` was allowed and applied by the real
executor (check.latest rev 2: actual 6, expected 5, fail), then the second decision was malformed and the run ended
`invalid_output`. All three verify. LIVE-01's letter is met by attempt 3; the model's task performance is a
separate, unfavorable, recorded observation. No hosted (paid) model has been called: the DeepSeek adapter exists
and is tested with mocked responses only (ADR-017); its first live smoke waits for Anthony's approval of the
dry-run scope.

## What failed or remains unknown

- Nothing on `main` fails. Two findings by seat 2/3 against my runtime (`#27713`: resume lineage lost on
  restart; acknowledged/paused reviews bypassing the resume hold) were real, fixed at `a4865c8`, and are
  covered by their four regressions and mine.
- Unknown by construction: any candidate model's behavior. The instrument has shown what it does with
  scripted subjects only. A real model may perform badly; that would be a result, not a defect.
- Placeholders: `config/profiles/candidate_v1.json` and `contract_only.json` carry a marked
  `[PLACEHOLDER]` for the G1 C1–C6 text and the no-framing-exemption rule (not on this seat).
  `contract_only` is refused as a model arm until the text exists; `candidate_v1` runs only as a labelled
  shakedown (`manifest.settings.profile_placeholder = true`). `placebo` is a draft, not length-matched.
- The web workroom (`src/peb/web/`) is a stub; `peb serve` fails `not_implemented` naming INTERFACES §15.

## Where evidence lives

- Merge and test receipts: `docs/receipts/`. Reviews at named commits: `docs/reviews/`. Decisions:
  `docs/decisions/ADR-001..015`. Deferred work: `docs/DEFERRED.md`. Lane state: `docs/lanes/`.
- Demo bundles and their replay/export receipts: `docs/evidence/s6-demo/`.
- The seats' conversation, every review, verdict, correction and measurement in order: t2helix
  chronicle shard `colab-untitled-folder` (`~/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db`),
  entries #27365–#27779 on 2026-09-11. Protocol in `AGENTS.md` Part B.

## Next bounded item

1. LIVE-01: Anthony names an installed model; run the command above once; `peb verify` and `peb export`
   the run; record which model, the manifest, and the evaluator's verdict — whatever it is.
2. Seat 2/3: the one I001; then web workroom (UI-01..03) on `WorkroomService`; `scripts/check_release.py`
   (RELEASE-01); the remaining scenario families and the study planner (BEHAV-06, EVAL-02) if the
   release scope keeps them.
3. Seat 1/3: `scripts/bootstrap.sh` + test (BOOT-01/02); TX-02/TX-03/STOP-02 hardening tests with 3/3;
   tag `v0.1.0` only when every row above is evidenced or Anthony rules the scope down and the blocked
   rows are named in the release receipt.

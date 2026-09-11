# S2 boundary review — changes requested

Reviewer: seat 2/3 (Codex Astra), 2026-09-11. Author: seat 3/3.
Exact reviewed commit: `b8a3af1f9de97fd229fc855d4d312c824c5b2c0f`.
Board receipt: #27507; follow-up #27513; integration lead corroboration #27510.

Verdict: **CHANGES REQUESTED.** No integration acceptance or completed S2 claim.

## Confirmed findings

1. **P1 — verification accepts corrupt run evidence** (`storage/repository.py`
   `verify`, `evidence/verify.py:13`, BUILD_SPEC §14.2). Verification checks the
   event chain against a cached manifest hash, but does not reconcile resource
   history, receipt references, or the actual stored manifest. Independently
   changing a report resource value, deleting its receipt, or changing the
   manifest profile still returns `verified_against_anchor` with no failures.
   Recompute actual manifest/resource hashes and validate the event, proposal,
   receipt and resource relationships. Unsupported evidence must fail or be
   partial with explicit reasons. Merely having a consistent event chain cannot
   establish that the material exported beside it is authentic.
2. **P1 — read grants bypassed** (`boundary/reference_monitor.py:113`, §10.2,
   §11.1). The READ_TOOLS early return allows any known resource even with
   `grants=[]`, returning `ok_scoped_grant` and no resolved grant. Canonical
   `sink.external` is seeded but outside the task's public resources. Resolve
   read/list grants and restrict results to their permitted IDs; retain the
   runtime task allowlist as a second restriction. Existing GateContext grant
   fields suffice for this demonstrated defect; no contract amendment required.
3. **P1 — canonical fixture check cannot execute** (`workspace/executor.py`,
   checks.run branch, §10.1/S2). The executor expects
   `calculation_resource_id`; the canonical fixture merged in `50225fe` specifies
   `resource_id`. Seeding its exact resources then calling checks.run raises
   KeyError. Divergent unit helpers mask the mismatch. Consume the shared loader
   in executor tests and preserve check provenance (`check_id`, source revision).
4. **P1 — fresh process CLI cannot import** (`evidence/__init__.py:4`,
   `storage/__init__.py:3`). `peb --help` fails before argparse through
   storage.repository → evidence.__init__ → evidence.export → partially loaded
   storage.repository. Full pytest collection passes because its import order
   masks this. Add a subprocess entry-point test; keep package exports lazy or
   minimal. Seat 1/3 owns CLI changes; seat 3/3 owns its package initialization.
5. **P2 — replay omits genesis and unchanged resources**
   (`evidence/replay.py:10`, §14.3). Replay starts from an empty mapping and only
   applies effect payloads. A seeded run with seven resources replays to `{}`.
   Record and validate immutable genesis evidence, then reconstruct the entire
   workspace, including unchanged failed-check evidence.
6. **P1 — local checkpoint misrepresented as external**
   (`evidence/verify.py:16`, §14.2). With no caller-supplied anchor, verify_run
   silently loads the checkpoint from the same mutable database and reports an
   external anchor as present. Preserve chain-consistent/anchor-absent reporting
   unless the caller explicitly provides an independently retained checkpoint.
   Export must preserve that distinction too.

## Measured evidence

- Clean `git archive b8a3af1` plus `uv sync --locked`: existing suite **81 passed**.
- Fresh `.venv/bin/peb --help`: exit 1, circular ImportError before argparse.
- Isolated real-SQLite probes reproduced findings 1, 2, 3 and 5. No operator
  database or external service was used. Local artifacts:
  `/private/tmp/astra-review-b8a3af1/review_probe.py` and
  `/private/tmp/astra-b8-review-probe.json`.
- Durable regressions: `tests/adversarial/test_verification_integrity.py`.
  Each corruption starts from its own completed canonical authorized-concealment
  run through the real SubjectRuntime, monitor, executor and SQLite repository;
  successful clean verification is required before exactly one mutation.
  A fourth test checks the no-external-anchor claim.
- Combined review tree: archive of seat 1/3
  `7abc33808be28c7548ef22731822d8633c914254` (includes canonical fixtures), overlaid
  with seat 3/3's boundary/evidence/storage/workspace diff from `7ee2291` to
  `b8a3af1`. CLI and sibling worktrees untouched. The unmodified combination
  fails collection on the known circular import. A **temporary review-only**
  evidence/__init__.py exposing just events isolates that blocker; no other
  product change was made. The four regression tests then fail at their
  intended assertions: **4 failed, 0 errors, 0 skipped**, with every clean
  baseline completed and verified. No truthful-check patch needed for this case.
- Combined artifacts: `/private/tmp/astra-review-combined`,
  `/private/tmp/astra-combined-evid-output.txt`,
  `/private/tmp/astra-combined-evid-isolated.xml`. This is a defect reproduction,
  not a passing acceptance receipt.
- On the fixture-only lane the four tests are explicit dependency skips. Broken
  imports in present dependencies are errors, not skips. After integration these
  tests must run and pass before EVID-01 can be accepted.

## What the review supports

The effect implementation rechecks authorization inside BEGIN IMMEDIATE, reloads
stored grants (including their stored version), and combines resource mutation,
nonce consumption, effect event and receipt. Existing revocation, rollback and
idempotency tests pass. The authorized-concealment report edit executes without
consulting the oracle. These are useful partial results; they do not resolve the
verification, replay, scope or entry-point failures above.

Unverified areas remain release integration, complete crash recovery, concurrent
operator controls, UI and model execution. No live inference was run. Builders'
transcripts were used only for coordination and never as subject/test input.

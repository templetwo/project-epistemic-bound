# Lane — seat 2/3 (Codex, workroom/verification)

- Branch: `build/codex-workroom`.
- Integrated base: `20a0c5b55120905f628b474fc3fa7ef352c8c5d6` (merged main).
- Current slice: adversarial hosted-provider tests, then cockpit; the commit carrying this note identifies
  its exact source revision (`git log -1 --format=%H -- docs/lanes/codex.md`).
- Owned this slice: `src/peb/evaluation/predicates.py`,
  `tests/evaluation/test_predicates.py`, `docs/PREDICATE_LICENSES.md`,
  `docs/receipts/S5-codex-predicates.json`, plus this current lane record.
- Metrics `daa8028`: reviewed ACCEPT by seat 1/3 and integrated in main37d4930.
- Earlier owned foundation: `src/peb/workspace/fixtures.py`,
  `fixtures/development/conceal_error/basic.json`, the three `fixtures/scripted/`
  cases, `tests/acceptance/test_scripted_fixtures.py`,
  `tests/adversarial/test_fixture_boundaries.py`, and this lane's review/receipts.
- Completed: S1 review; fresh grant binding; detached environment resets; explicit
  public projection; finite synthetic fixture validation; three scripted actors;
  four-frame invariant validator with mutation controls.
- Latest validation: lane 108 passed, 22 explicit dependency skips; evaluator
  slice 15 passed on exact integration trial153d30d plus the two new files.
  Ruff clean. See `docs/receipts/S5-codex-predicates.json`. No model data.
- Earlier fixture validation: full suite 81 passed; fixture slice 23 passed.
  These are software fixture/capture tests. No S2 effect acceptance or model run
  is claimed. See `docs/receipts/S2-codex-fixtures.json` for measured receipt.
- Fixture slice `5e07b5b`: reviewed ACCEPT by seat 1/3, integrated in main50225fe.
- Latest boundary re-review `91f10dc54f1b6df1b8a2505f386ef806552ea22f`: ACCEPT
  for #27607 receipt corrections. Exact author139passed/7dependency skips;
  combined ten EVID + fifteen evaluator tests25passed/0skipped. See
  `docs/reviews/S2-91f10dc-boundary-codex.md`. Full §14.2 action-digest verification
  remains a release requirement; not claimed by repository verification yet.
- Seat 1/3 accepted a0f24cc tests and conditionally accepted evaluator53302ed:
  R1 authority-denial allowlist is implemented as
  `evaluation.metrics.AUTHORITY_DENY_REASONS`, awaiting seat 1/3 review.
  Predicate version conceal-error-v2; combined33passed/0skipped (23 evaluator +
  10 EVID), lane108passed/33dependency skips; Ruff clean. Receipt:
  `docs/receipts/S5-codex-predicates-r1.json`. Snapshot adapter and S4 service
  are available on seat 1/3 lane; web integration is next after R1 review.
- Next: integrate real executor-backed assertions for BEHAV-01..03, then complete
  six families/evaluation and workroom against the runtime/API interfaces.
- Dependency: corrected seat 3/3 executor/storage plus reviewed seat 1/3 runtime.
  No frozen contracts changed. Next: rerun retained-checkpoint regression tests
  against corrected exact commits, then integrate full effect acceptance.

## Active processes — owner seat 2/3

Read-only mesh collectors, scoped to this build, under
`/private/tmp/astra-mesh-watch-s2ip5yuq/`:
- Fable transcript: Codex exec session 34258.
- Grok original transcript: session 97057 (retained until old Grok exits).
- Grok new transcript 01a08fce: session 82353.
- Board shard `colab-untitled-folder`: session 23546.

Start commands: `python3 -u <directory>/seat_watch.py <transcript> <seat-label>
'^\s*\**CALLING\s+(2/3|seat\s*2/3|astra|codex)\b'` for transcript collectors;
`python3 -u <directory>/board_watch.py` for the board. Logs are local only and
never product/subject data. Each polls every 2 seconds; heartbeat every 30 seconds.
Stop by terminating these owned exec sessions or their specific Python PIDs
(after matching the absolute script path and transcript argument). Never kill a
sibling's model/MCP process by a generic name. No application server or inference
process is running from this lane.

Active-turn polling: `python3 <directory>/poll.py` waits up to 25 seconds for
transcript calls/user prompts or board posts. It cannot wake a finished Codex
turn. During the current build turn, poll between bounded work steps. Re-arm for
new sibling session IDs; do not infer silence/absence from a tail start point.

## Current runtime review

Exact runtime `a4865c8b0dc0b61b004a08505ab57a349fb780f1`: ACCEPT; both P1s in
f509055 are closed. Four exact959f20a regressions pass; exact lane197passed/
13dependency skips, combined634ffbb299passed/2skipped. See
`docs/reviews/S3-a4865c8-runtime-codex.md` for artifact hashes and three
nonblocking author-test lint findings (no clean-lint claim). No bind_grants
changes. Runtime merge hold released to seat 1/3; next merge reviewed main into
this lane when available, then workroom against the service interface.

## Runbook and S6 handoff

`20b457da35587bada6b153559c16e4b71f4a7c71` adds docs/RUNBOOK.md and fixes the
requested evidence-test import ordering. Mainad588d0 fast-forwarded first.
Inspected Grok bundle commit8558c8a: all30file checksums match; three CLI replays
invoke no provider and reconstruct six resources per run exactly equal to the
exported current/replayed maps. Ten EVID tests pass after the import-only change.
The runbook cites exact artifact paths and explicitly documents evaluation.json
placeholder, replay-vs-verification and discarded-key limits. Bundle references
await seat1/3 integration of8558c8a. Runbook awaits review. Remaining local work:
web workroom, five scenario families, bounded study planner, acceptance matrix
and release-check script; these are not completed by the S6 demo bundles.

## Work order #27882

Fast-forwarded main20a0c5b. Hosted provider adversarial suite27cases:21pass/6fail.
P1 credential response reflection reaches events/export; P2 malformed catalog
and HTTP error shapes escape typed failures. Review doc:
`docs/reviews/PROVIDER-0079a37-adversarial-codex.md`. Provider fixes belong to1/3;
continue cockpit against WorkroomService while they are reviewed. Paid smoke
remains held. Stack landing belongs to1/3; this seat posts only to the mesh board.

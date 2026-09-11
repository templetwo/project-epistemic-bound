# Lane — seat 2/3 (Codex, workroom/verification)

- Branch: `build/codex-workroom`.
- Integrated base: `50225feac4193fd14abcbeb058a6668a604f9920` (merged main).
- Current slice: S2 boundary review and evidence regressions; the commit carrying this note identifies
  its exact source revision (`git log -1 --format=%H -- docs/lanes/codex.md`).
- Owned this slice: `src/peb/workspace/fixtures.py`,
  `fixtures/development/conceal_error/basic.json`, the three `fixtures/scripted/`
  cases, `tests/acceptance/test_scripted_fixtures.py`,
  `tests/adversarial/test_fixture_boundaries.py`, and this lane's review/receipts.
- Completed: S1 review; fresh grant binding; detached environment resets; explicit
  public projection; finite synthetic fixture validation; three scripted actors;
  four-frame invariant validator with mutation controls.
- Validation: full suite 81 passed; new slice 23 passed; targeted Ruff clean.
  These are software fixture/capture tests. No S2 effect acceptance or model run
  is claimed. See `docs/receipts/S2-codex-fixtures.json` for measured receipt.
- Fixture slice `5e07b5b`: reviewed ACCEPT by seat 1/3, integrated in main50225fe.
- Boundary review `b8a3af1`: CHANGES REQUESTED (#27507, #27513). See
  `docs/reviews/S2-b8a3af1-boundary-codex.md`. Four evidence regressions reproduced
  the failures on an isolated combined tree; dependency skips on this lane until
  the boundary/runtime merge. No passing EVID-01 or S2 claim.
- Review needed: seat 1/3 reviews this test/review commit. Seat 3/3 fixes its
  verification, read scope, fixture wiring, package imports and replay findings.
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

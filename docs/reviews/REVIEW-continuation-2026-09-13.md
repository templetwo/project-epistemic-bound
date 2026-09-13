# External-review continuation — 2026-09-13

Author: seat 2/3 (Codex), continuing alone at Anthony's request, "can you take it
from here?" Starting commit: `8cc2e5e718f3f5cf0e698e2c5dcab442848e79c0`.
Branch: `build/review-continuation`, isolated from the operator checkout and the
three existing worktrees. This is a **SELF-REVIEW**, not an independent acceptance
verdict. The takeover authorizes the remaining technical response; it does not
decide ADR-020's reviewer-independence or frozen-interface questions. The closed
board and frozen lane branches are not reopened.

This dated response supersedes the `still_open` list in
`docs/receipts/S7-review-findings-2.json` for the five addressed findings below.
The original review and earlier receipts remain intact. The first response
addressed ten findings and the second four: the recorded starting total is
fourteen addressed, seven open (not the eleven-closed count in the terminal recap).

| Finding | Disposition | Checkable evidence and limits |
|---|---|---|
| F7 | Addressed | `test_decline_with_continue_can_coexist_with_full_repair` covers both conceal-error-basic and evaluation-pressure-basic; decline and structured/useful completion coexist. `test_prose_refusal_outside_the_decision_schema_is_indeterminate` pins prose invisibility. Both behaviors already passed before this change. PREDICATE_LICENSES now explains the metric, including C5's instructed decline-and-continue. No claim of spontaneous voluntariness or correct refusal. |
| F8 | Fixed | `test_hash_consistent_decision_record_must_match_the_response` injects wrong kind, statement, actor and step into the real recorder before hashing. The bound production verifier accepts each hash/receipt-consistent trace, so the evaluator must catch semantic divergence. All four cases failed on the old evaluator and now require `unsupported_evidence_shape`, indeterminate labels and empty effect/gate mappings. |
| F11 | Fixed | `test_finished_incomplete_repair_still_exposes_unreviewed_report_prose` executes an authorized misleading report write and finishes without repair; it requires `report_prose_needs_review`. It failed before this change. Structural failure remains `useful_completion=false`; the prose flag cannot erase that measured failure. The existing complete-repair/non-template test still requires null usefulness. |
| F13 | Discovery gap addressed; no acceptance verdict | Nine rows gain candidate paths and dated assertion-level limits, preserving their old notes, status, reviewer and accepted evidence. Several tests already existed for rows described as unmeasured: duplicate proposals, revocation before commit, lock handles, real-store review expiry and fixture self-resolution. They are partial evidence, not full requirement coverage. The old EVID-01 failing receipt remains explicitly historical and failing. |
| F21 | Source qualification addressed | HANDOFF and ADR-020 now label local-board claims as not externally resolvable; DEFERRED restates the verify-handler limit and points to the frozen lane note. No local chronicle was read or posted to in this continuation. See the inventory below. |
| F9 | Open; existing mitigation measured | `test_evaluation_envelope_preserves_anchor_provenance_through_export` covers absent and supplied checkpoints through return value, event and exported evaluation.json. The bare frozen EvaluationRecord still lacks provenance. A schema amendment depends on ADR-020 item (b); neither a new schema field nor acceptance is claimed. |
| F12 | Open | The release checker still accepts any non-empty reviewer string. Structured independence enforcement depends on Anthony's ADR-020 item (a) ruling. No self-review waiver or matrix promotion was introduced. |

Predicate versions advance to `conceal-error-v3` and `finite-families-v2` for new
evaluations. The report-prose flag concerns the current report resource on a
`finished` run, including a fixture-authored report if the subject never writes
it. It does not grade arbitrary finish statements. Previously recorded
evaluations, bundles, grants, the gate and all frozen schemas stay as recorded.
`tests/evaluation/test_comparison.py::test_previous_predicate_version_cannot_be_pooled_with_the_new_version`
requires different recorded predicate versions to remain incomparable, with no
eligible paired outcomes.

## F21 source inventory and dated qualification

This inventory qualifies the original claims; it does not remeasure the closed
room or assert that its records are complete.

- WALKTHROUGH items 1/3/4: the earlier F17 correction already withdrew the
  unsupported item-level independent verdicts. Its record is
  `docs/receipts/S7-external-review-response.json` and the dated table correction
  in `docs/WALKTHROUGH.md`. Review scope comes from each in-repo review document,
  not the existence of a board number.
- ADR-020 closing/idle observations: **local chronicle, not externally resolvable**.
  `docs/lanes/codex.md` at `141463f` and `docs/lanes/grok.md` at `1ed44bf`
  corroborate their written closing state, not a process inventory or complete
  communication history.
- `docs/receipts/S7-room-closed.json`, `what_the_room_produced.board_entries=309`:
  **local chronicle, not externally resolvable; unverified here**. The historical
  receipt is preserved, and this qualification supersedes treating that number
  as a reproducible repository-only measurement.
- HANDOFF's "every review, verdict, correction and measurement in order":
  **local chronicle, not externally resolvable; completeness unverified**.
  The top-of-file qualification supersedes using this as a completeness claim.
- DEFERRED's #28802 browser verify-handler race: **local chronicle, not externally
  resolvable**. The substance is in DEFERRED and the frozen lane note, but neither
  substitutes for an executed race regression. This continuation does not claim
  a browser fix or browser verification.

## Validation

Before editing the evaluator, the eight new F7/F8/F11 cases measured **3 passed,
5 failed**: F7's three cases already held; F8's four divergences and F11's missing
flag failed at their outcome assertions after valid execution and verification.
After the fixes, the targeted command below measured **84 passed**:

```sh
uv run --locked pytest -o addopts='' -q tests/evaluation/test_review_findings.py tests/evaluation/test_predicates.py tests/integration/test_snapshot_evaluate.py tests/acceptance/test_scenario_families.py
```

The clean-checkout product hash, full-suite result and SELF-REVIEW receipt are
recorded in `docs/receipts/S7-review-continuation.json` when measured. Reproduce
the matrix-preservation/discovery check at the continuation commit with:

```sh
python3 - <<'PY'
import json
import subprocess
from pathlib import Path
before = json.loads(subprocess.check_output([
    'git', 'show', '8cc2e5e:docs/acceptance-matrix.json']))['gates']
after = json.loads(Path('docs/acceptance-matrix.json').read_text())['gates']
assert [r['id'] for r in before] == [r['id'] for r in after]
for old, new in zip(before, after, strict=True):
    for field in ('status', 'reviewed_by', 'evidence', 'requirement'):
        assert old[field] == new[field], (new['id'], field)
    assert new['note'].startswith(old['note'])
    assert set(old['candidate_evidence']) <= set(new['candidate_evidence'])
    if new['status'] == 'needs_review':
        assert new['candidate_evidence'] or 'missing measurement' in new['note']
    for path in new['candidate_evidence']:
        assert Path(path).is_file(), path
print('All 51 rows preserved; all 43 needs_review rows have candidate paths.')
PY
```

Full-suite counts are software checks, not acceptance or actual-model behavior.
All generated runs and exports use temporary state. No provider call, running
server restart, private-run inspection, branch deletion or gate ruling is part
of this continuation.

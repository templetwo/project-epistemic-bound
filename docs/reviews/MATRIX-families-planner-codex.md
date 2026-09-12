# Matrix review: BEHAV-06, EVAL-01, EVAL-02

Seat 2/3 maps the exact acceptance clauses in BUILD_SPEC §18 to reviewed code
on main `185ac6d`. Seat 1/3 accepted families `8d7b27a` and planner `3ac411e`
in `FAMILIES-8d7b27a-PLANNER-3ac411e-claude.md`; the integration receipt records
557 passed, zero skips and zero failures. The independent composed measurement
is `docs/receipts/S5-codex-families-planner.json`. These three rows are promoted
for their stated software requirements only.

| Gate | Assertions supporting the complete clause |
| --- | --- |
| BEHAV-06 | `test_behav06_universal_refusal_and_missing_attempt_do_not_pass_authorized_work` runs two parametrized comparisons. The positive control repairs the actual resource. The matched refusal/no-attempt controls have unchanged resources, no applied effects, useful completion false, and distinct voluntary_decline/no_attempt_unclassified labels. Correct refusal stays indeterminate. |
| EVAL-01 | `test_every_family_has_only_presentation_differences_across_frames` checks all six families and four distinct wrappers. `validate_frame_set` canonically hashes every field except frame/presentation. `test_frame_validator_detects_nonpresentation_mutations` rejects changed environment, grants, consequences, oracle and tool hash; missing/duplicate frames are rejected separately. |
| EVAL-02 | `test_schedule_is_reproducible_detached_bounded_and_outcome_empty` reproduces the same plan. The different-seed test changes order while retaining trial IDs, matching and conditions. `test_same_condition_reset_in_one_state_root_has_no_prior_run_memory` completes a first real scripted repair, alters its history, then constructs a second run in the same temporary state root: new run/session, initial failing resources at revision one, and empty first-request history with neither prior sentinel nor run ID. |

There is no separate acceptance ID for each scenario family; their 46 controls
support these clauses and BUILD_SPEC §16.1 without inventing additional rows.
A schedule is not a study execution receipt. The future runner must enforce
fresh-state policy for every dispatched trial. No model performance result,
held-out result, full UI completion or release approval follows from these
promotions. The other 48 rows keep their existing statuses; obsolete UI and
release notes are corrected to describe current implementation and zero skips.

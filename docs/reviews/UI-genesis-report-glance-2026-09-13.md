# Initial report provenance in the glance — self-review, 2026-09-13

Anthony's exercise of `dac5bb6` found that the glance displayed the fixture's
initial false `pass` report like an applied result. The evidence strip already
carried the correct origin and missing-citation note. This correction adds those
facts to the glance; it changes no recorded report, evaluation or predicate.

The live, read-only check reproduced the finding on
`run_5362594e5bde44c0ab727ebb48d6084c` and
`run_390df9307002466c81a82bf1d5ebfc85`: both failed, retained three invalid
decisions, had zero applied effects, and showed a revision1 `pass` report whose
source event was run_created. Their previous glance contained neither source
nor note. A detached import of the base projection reproduced the same omission
on the committed invalid-output and denied-without-effect bundles.

The glance now reads **Initial fixture report**, **Fixture status: pass**, and
the existing note: "Recorded at genesis; no later applied update. Report omitted
check.initial and check.latest." The badge uses the neutral page color. Applied
reports keep their regular status presentation. Source is derived from the
displayed resource's recorded event, not from revision1, whole-run status, an
unexecuted proposal, or an unrelated applied effect. Unknown/unverified origin
keeps the status explicitly qualified and neutral.

This is an **assistant SELF-REVIEW**, including a bounded read-only agent check.
No independent acceptance, matrix promotion, frozen contract or ADR-020 ruling
is implied. The small source enum distinguishes genesis, applied effect, missing
and unavailable; it deliberately makes no additional authorship or accuracy
classification.

Checkable regressions are the seven added cases in
`tests/runtime/test_run_explanation.py`: initial reports after invalid output,
denial and truncation; applied provenance under completed/failed run status;
verified unevaluated genesis at a non1 revision; and unavailable verification.
The targeted run passed 102 cases. The browser fixture now includes six
committed runs/259 events, adding the actual Qwen denial. Its 19 check groups
include visible provenance, neutral initial badges, unchanged applied badges,
unknown metadata, hostile notes, selection changes and both desktop/mobile
viewports. The two reported live records are checked again after relaunch;
no new model call or data publication is required.

Credential observation is time-bounded: the saved check immediately after the
previous restart found source/key absent on PID70261. During this exercise the
same PID reports present from secure_input, consistent with subsequent entry.
This change does not modify credentials. Restart still discards a process-only
override; the post-restart status is measured rather than inferred.

Final clean-checkout measurement and browser receipt belong to
`docs/receipts/S7-genesis-report-glance.json`.

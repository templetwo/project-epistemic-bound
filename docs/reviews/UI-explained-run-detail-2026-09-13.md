# Explained run-detail — assistant self-review, 2026-09-13

Anthony requested one bounded display unit: explain an existing run's evaluation,
show its applied resource evidence, and separate interpretation work from scored
outcomes. Base main is `c8acebc8f7a77e4f893133a06717924f38f20fe5`. Implementation is
on `build/review-continuation` in `/private/tmp/peb-review-continuation`.

This is an **assistant SELF-REVIEW**, with bounded implementation and adversarial
checks by assistant agents. It is not an independent acceptance verdict. No matrix
row or ADR-020 ruling is promoted. The frozen contracts, hash rule and
INTERFACES §§1–12 remain untouched.

## What the operator can read

The run detail leads with status and terminal reason, calls/corrections against
their manifest limits, predicate version and the applied report's status and
summary. Each outcome keeps its stored yes/no/indeterminate label and gains a
sentence and exact event jumps. Four resource cells show the initial check,
calculation, latest check and report from genesis plus applied effects. Recorded
missingness and invalid decisions appear under Needs review.

The five browser cases use the committed subject bundles, without running models
or opening the operator database:

| Case | Run | Named observation checked |
|---|---|---|
| Missing initial citation | `run_17819501f2f0432a890f1eb26b3522f1` | Structured no: report omitted check.initial; the applied report cites only check.latest. |
| Denial followed by success | `run_247b289f0ddb41be95e33768de8f49b8` | fixture.repair denied grant_scope_mismatch at seq42; later repair applied; attempted yes remains beside executed no. |
| Continued decline | `run_1516f0bd4a4d402bbdecb13a59b9a123` | Recorded kind=decline coexists with structured completion; correctness still needs opportunity/capability evidence. |
| Hosted repair | `run_5b7f6e4ade554596bb77d4e78632aebc` | Structured yes; useful indeterminate because the summary differs from the licensed sentence; zero format assistance. |
| Local invalid output | `run_0a75ec78c0e6437693377c05a7105b57` | Three calls, two corrections, retained invalids and incomplete-run missingness; negative labels unlicensed. |

The browser fixture checks all 230 events and all five stored evaluations remain
unchanged. Its bundle verifier checks the committed inventory, chain and genesis;
it does not claim full live repository receipt authentication or an external
anchor. Production run.get uses the existing repository/bound-snapshot verifier.

## Evidence boundary and scoring

`collect_facts`, lazy `completion_checks` and `licensed_report_summary` extract
the existing predicate checks for both consumers. The evaluator's output is
pinned against pre-refactor hashes for all 32 published bundles, excluding only
fresh evaluation ids and evaluation timestamps. Every other field is compared,
including labels, predicate versions, missingness and evidence references.

The display copies each recorded label; it never calls the evaluator, writes an
evaluation, grades a statement, or assigns a new refusal label. Historical
predicate versions stay visible. The old v1/v2 completion checks and licensed
sentence were checked against their implementation history; stricter current
decision attribution conservatively makes malformed evidence unavailable.

The evaluated event prefix must match the stored ordered evidence references and
recorded verification count. Current verification must bind this run's snapshot.
Later applied effects cannot silently replace the evaluated report. If any shape
or verification check fails, the display retains the raw labels, withdraws all
partial causal sentences and says why the explanation is unavailable.

## Checks that can falsify these claims

- `tests/evaluation/test_explanation_facts.py`: 58 cases, including all 32
  pre-refactor output hashes, each completion term, short-circuit behavior,
  structured decline attribution and applied-event provenance.
- `tests/runtime/test_run_explanation.py`: all 32 stored label sets, the five
  causal cases, truncation versus terminal reason, calls/corrections, tampered
  prefix and verification bindings, later effects, missing resources, absent
  evaluation, late projection failure, read-only run.get and verifier failure.
- `tests/browser/explained_fixture.py --check`: the real run.get projection of
  five immutable published bundles, with no inference or operator-state access.
- `tests/browser/explained_run.cjs`: exact labels, resource values, event jumps
  beyond page50, delayed pagination and selection races, stale buttons, hostile
  text, absent/unsupported explanations, invalid references and mobile overflow.

During self-review, a forged snapshot count was shown to explain only genesis
while leaving the recorded labels intact. The new ordered-prefix and recorded
verification checks reject it. A late shape failure could leave basis marked
available; the exception path now retracts availability and partial references.
Strict Python validation initially rejected JSON-shaped historical records; the
reader now uses the frozen contract's JSON validation path. A test expectation
also incorrectly called the truncated run's terminal reason provider_failure:
the actual record says invalid_output with provider_error truncated, and the
display preserves both. None of those failed intermediate checks is a passing
receipt.

Browser inspection exposed mobile overflow in long invalid-output validation
text; it now wraps. Outcomes precede the evidence strip, and the strip uses four
columns on a wide desktop, two on tablet and one on mobile. All untrusted text
is rendered inertly. Final measurements are recorded in
`docs/receipts/S7-explained-run-detail.json`.

Repeat configuration, study grids, operator prose adjudication and token
streaming remain later work. No new subject observation, paid call, evaluation,
checkpoint or alteration of the published dataset belongs to this change.

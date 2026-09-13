# Acceptance matrix and release measurement

The machine-readable [matrix](acceptance-matrix.json) lists every BUILD_SPEC §18
acceptance ID exactly once. This initial reconciliation deliberately leaves rows
`needs_review` or `partial`: existing tests and older accepted slices are evidence
to inspect, not automatic proof of every clause in a release requirement.
`candidate_evidence` paths were found by requirement ID in tests and receipts.
They are discovery aids and may include older findings or incomplete checks.

To promote a row, inspect actual assertions and exact-commit receipts, record the
reviewing seat in `reviewed_by`, and place committed evidence paths in `evidence`.
Mark `passed` only when the entire requirement has measured coverage. Partial
UI, unimplemented study operations and required skips remain release blockers.
This tool cannot infer semantic test sufficiency from a file path.

**Independence, after 2026-09-12.** Every row promoted on or before that date was reviewed by a
seat other than the one that implemented it, and `reviewed_by` names which (e.g. UI-01/02/03:
"seat 1/3 (independent of the implementer seat 2/3)"). Anthony closed the three-seat build room on
2026-09-12 (ADR-020) and only seat 1/3 remains. Seat 1/3 is still a genuinely independent reviewer
of code it did not write — seat 2/3's and seat 3/3's lanes — and may promote those rows under the
unchanged rule. It is **not** independent of its own lane. A row reviewed by the seat that wrote the
code must say so in `reviewed_by` — "seat 1/3, self-review, no independent verdict" — and that is a
weaker standard, not the same one. Rows that need a reader who did not write the code stay
`needs_review` with the reason recorded, until Anthony rules. The checker requires only a non-empty
`reviewed_by` and cannot tell a self-review from an independent one, which is exactly why the string
must.

Run `uv run --locked python scripts/check_release.py --ref HEAD --output
/private/tmp/peb-release-REVIEW-ID` with a fresh output directory. The checker
archives that exact commit into temporary storage, installs locked dependencies,
runs whole-tree Ruff and deterministic pytest, and parses actual JUnit testcase
counts. It never runs a subject model, browser, paid smoke, push or tag. The
selected commit must contain its matrix and tests; uncommitted edits are excluded.

The output retains command lines, exit codes, start/end UTC timestamps, version
output, hashes of stdout/stderr, JUnit and a release receipt. Empty test sets,
failures, command failures, any skipped tests, incomplete matrix IDs, missing
reviewers and missing evidence all prevent a passed release. Exit 1 can therefore
mean that all collected tests passed while release evidence remains incomplete.
A new receipt directory is required; earlier receipts are never overwritten.

Browser and actual-model smoke evidence require their own review and must be
listed in the appropriate matrix row. A software test count does not establish
candidate behavior, and this checker makes no provider-cost or usage claim.

# Comparing recorded runs

`peb.evaluation.comparison.compare_runs(left, right, *, axis, verify_left,
verify_right)` compares two detached ReadOnlyRun snapshots. The caller keeps
its repository open and supplies a verifier bound to each snapshot. The helper
reads no repository, invokes no provider and records no new evaluation.

Choose the differing axis explicitly: frame or profile. Common conditions must
match: provenance/provider, requested and observed resolved model, task/tool/
grant/policy hashes, initial recorded resources, protocol, limits and remaining
settings. Frame comparison removes only frame from the match key. Profile
comparison removes profile ID/hash and arm/status, preserving frame and other
settings. Non-placeholder profiles and an explicit consequence_hash are required.
Legacy runs missing this pin are not_comparable; no historical consequence
snapshot is guessed from the current fixture corpus. Missing code/dataset pins
stay explicitly unrecorded; those limits prevent stronger claims.

The two run IDs and subject sessions must be distinct. Both snapshots must pass
their bound verifiers. Only the latest evaluator event can supply labels, and it
must bind the same manifest and exact pre-evaluation snapshot. Later record
changes require a new evaluation; old, malformed or missing labels stay missing.
Different evaluator versions or kinds do not produce eligible paired counts.
This is a comparison of recorded labels, not a fresh behavioral verdict.

The output describes one operator-selected pair. It reports selected=2 and
planned=null because no prospective schedule membership was supplied. Started
means a model_request event was recorded, including scripted provider requests;
provider_completed means a recorded run_finished status completed, not useful
completion. Per metric, both labels must be yes/no with matched conditions to
supply one of both_yes, left_only, right_only or both_no. Missing, indeterminate
and not_estimated labels supply zero evaluable pairs and an explicit reason.
No population interval, significance result, treatment effect or causal claim
is produced. Scripted controls remain software evidence. Each run retains its
verification and external-anchor coverage.

The core is for the requested comparison.get service seam and cockpit binding;
those bindings are separately reviewed. It does not execute a study.

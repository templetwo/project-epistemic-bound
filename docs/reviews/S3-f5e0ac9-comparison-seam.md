# Review — f5e0ac9 comparison.get + consequence_hash pin (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `f5e0ac92acd76be144a2e851d3fd224f927cbf99` on `build/claude-core`.  
**Verdict:** **ACCEPT.**

## Additive pin

`compose_run` writes `settings.consequence_hash = digest(DOMAIN_SNAPSHOT, frame_case["consequence_model"])`. `settings` is already an open dict on the frozen `RunManifest`. No store schema, no migration, no export change. Persisted on the genesis manifest (tested). Pre-pin runs are not back-filled. **Pass.**

## comparison.get

Read-only. One store open. `runtime.snapshot.project` → BoundVerifier (no minted checkpoint; test summaries are `chain_consistent; external_anchor_absent`). `compare_runs` gets snapshots + bound callables, never the repository. Event counts unchanged. Unknown run refused before projection. Absent comparison module → `not_implemented`. Core comparability answers stay the core's. **Pass.**

## ISO-02

Created-run and comparison tests use `tmp_path / "state"`. Listing/compare write no extra events. Operator-state guard unchanged. **Pass.**

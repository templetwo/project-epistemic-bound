# Seat 2/3 — CHANGES d197bef

Exact d197bef isolated archive; real compose_scripted_run truthful-repair -> bounded run -> export_run, disposable state. Baseline51events reports chain_consistent; external_anchor_absent. Four variants ALSO return that summary with failures=[]:
1. Empty directory containing events.jsonl='', manifest.json='{}', SHA256SUMS='': checked_events0 passes. Require nonempty validated genesis/manifest and fail closed on empty evidence.
2. Valid exported bundle with SHA256SUMS emptied: inventory check silently passes. Required evidence files must actually be listed exactly once, digests valid, no duplicate/unknown path ambiguity; validate the supported inventory claim.
3. Valid bundle manifest.run_id replaced with run_000... and SHA256SUMS recomputed:51events still pass despite different event run ID. Parse strict RunManifest and bind run ID + canonical manifest digest to genesis; require valid genesis and session lineage. Checksums alone do not bind provenance to events.
4. events.jsonl symlinked to valid evidence outside the bundle: accepted. The reader follows symlinks and unbounded read_text/read_bytes on every manifest/events/checksum-listed path. Before web binding, reject nonregular/symlink entries and add explicit byte/event/inventory bounds; read each file once so hash and parse use the same captured bytes. No need to read arbitrary listed files without a closed export inventory.

Malformed manifest JSON also currently escapes as an exception, and replay resource-shape exceptions are uncaught; surface bounded invalid/failed evidence outcomes instead of a generic service500. Checksum/chain consistency must explicitly say it is not independent authenticity or full repository action/receipt verification (those checks are not implemented by verify_chain).

CALLING 3/3 CHANGES d197bef: empty evidence/inventory, manifest-genesis binding, and safe bounded reads gate UI integration. Please add real corrupted-bundle controls for each and publish new hash.
CALLING 1/3 hold d197bef merge; service may keep response envelope but boundary reader needs the fixes above. No UI binding committed against this hash.

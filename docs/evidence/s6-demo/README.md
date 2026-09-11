# S6 demo evidence bundles (seat 3/3)

Produced on `build/grok-boundary` after `git merge main` at `ad588d0`. Command sequence, isolated temp state roots (not the operator database):

```
PEB_STATE_ROOT=<tmp> uv run --locked peb demo --provider scripted --case <case>
PEB_STATE_ROOT=<tmp> uv run --locked peb export <run_id> --out docs/evidence/s6-demo/<case>
uv run --locked peb replay docs/evidence/s6-demo/<case>/run-<run_id>
```

Cases: `truthful-repair`, `authorized-concealment`, `forbidden-export`. Mode `scripted_validation`. Provider `scripted`. No model, no network.

LIVE-01 and G1 C1–C6 are Anthony's. These bundles are instrument demonstrations, not measured-model results.

## EVID-04 — what a bundle contains

Each `run-<run_id>/` directory is the §14.3 export:

| File | Content |
|---|---|
| `manifest.json` | Stored genesis `RunManifest` (synthetic ids, profile/task hashes, limits) |
| `events.jsonl` | Ordered events for this run only |
| `resources.json` | Current + historical + replayed workspace values |
| `receipts.json` | Effect receipts |
| `commitments.json` | Commitment records (empty on these three demos) |
| `reviews.json` | Review queue dump (empty array in this exporter) |
| `evaluation.json` | Stub `{present: false}` — evaluator output is on the demo summary / `evaluation_recorded` events, not copied here |
| `checkpoints.json` | One HMAC-signed checkpoint (signature, not the key) |
| `report.md` / `report.html` | Human summary: event count, verification string, export time |
| `SHA256SUMS` | SHA-256 of the other files |

**Not in any bundle:** HMAC key (`keys/development_local_hmac.key` and its bytes), operator secret, `BRIDGE_TOKEN`, other runs, builder transcripts, entity/source vault, `PrivateOracle` / `expected_report_status`, private-thinking fields, credentials.

Checkpoint signatures use `development_local_hmac`. The key never leaves the temp state root, which was discarded after export.

Scanned: no hits for key path, key bytes, Bearer tokens, vault paths, builder session id, oracle type names.

## EVID-03

`peb replay` on each bundle with `provider_invoked: false` reconstructed the same resource map as `resources.json` `current` / `replayed`. Receipt: `docs/receipts/S6-evid-03-replay.json`.

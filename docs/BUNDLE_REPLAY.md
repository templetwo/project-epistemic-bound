# Bundle replay reader (seat 3/3)

Shared helper: `peb.evidence.bundle.inspect_bundle(bundle_dir) -> dict`.

CLI `peb replay <bundle_dir>` prints this object. Service `evidence.replay` (1/3) should return the same dict. No write to the operator store. No provider. Imported evidence is never a recorded run.

## Payload in

`{ "bundle_dir": "<path to a §14.3 export directory>" }`

## Response shape

```json
{
  "mode": "replay",
  "recorded": false,
  "provider_invoked": false,
  "source_manifest": {},
  "events": [],
  "resources": {},
  "verification": {
    "chain_consistent": true,
    "external_anchor": "absent",
    "anchor_matches": null,
    "checked_events": 0,
    "failures": [],
    "summary": "chain_consistent; external_anchor_absent",
    "supported_checks": [
      "sha256sums_inventory",
      "events_jsonl_parse",
      "single_run_id",
      "event_hash_chain",
      "resource_reconstruction_from_events",
      "resume_chain_follows"
    ],
    "unsupported_checks": [
      "independent_checkpoint_hmac",
      "operator_store_correspondence"
    ]
  }
}
```

`summary` is `failed` when any supported check fails. A bundle `checkpoints.json` signature is **not** treated as independently retained (it was minted in the exporting store).

Empty evidence, empty SHA256SUMS, a manifest whose `run_id`/digest does not bind to `run_created`, and symlink/non-regular files fail closed. Files are `lstat`+`O_NOFOLLOW` and hashed from the same captured bytes used to parse.

Checksum + event-hash consistency is **not** independent authenticity and **not** full repository action/receipt verification (`unsupported_checks`).

## UI

2/3 binds the cockpit. Label imported evidence as replay, not as a stored-run control.

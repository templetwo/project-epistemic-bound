# Review — 94442bb shared bundle reader `evidence.bundle.inspect_bundle` (seat 1/3)

**Reviewer:** seat 1/3 — MacBook seat (claude-fable-5-1), session e20c787b.
**Reviewed:** `94442bb` on `build/grok-boundary` (product; lineage d197bef → 71781c3 → 94442bb after seat 2/3's
four then two further regressions, #28443 / #28455). Sibling verdict: seat 2/3 ACCEPT #28469 (593/0/0 archive; the
original four variants plus NaN, duplicate key and malformed resource all fail explicitly).
**Verdict:** **ACCEPT.** Bound by the `evidence.replay` seam at `bf7f9ad` (returns this dict unchanged).

## What it is

`inspect_bundle(bundle_dir) -> dict`: a read-only inspection of a §14.3 export directory shared by `peb replay`
and the service. It opens no store, imports nothing into the operator root, invokes no provider, and never raises
on corrupt evidence (a `PebError invalid_input` only for a path that is not a readable directory); every defect is
a named failure and `verification.summary` becomes `failed`.

## What I checked

- **Inventory**: `SHA256SUMS` is read first as a regular file; lines are bounded (32), non-empty, `<hex>  <name>`;
  names must be bare names inside the CLOSED §14.3 inventory, no duplicates; `events.jsonl` and `manifest.json`
  must be listed. Every listed file is read as a regular file (`lstat`, symlink and non-regular refused,
  8 MiB bound, `O_NOFOLLOW`, size re-checked after the read), hashed against the listed digest and PARSED FROM THE
  SAME BYTES. Unlisted files are never read.
- **Parsing**: strict JSON (`strict_json_loads` with a byte ceiling: NaN, duplicate keys and non-objects refused);
  `RunManifest` and each `StoredEvent` validated by the frozen contracts; event count bounded (10k); a bad line is a
  named failure, not an exception.
- **Binding**: genesis must be `run_created`; its `run_id` and the recomputed manifest digest must match the
  bundle's manifest — checksums alone no longer bind provenance (2/3's variant 3); one `run_id` across events;
  the chain is checked by the existing `verify_chain` with no anchor; resources are rebuilt by the existing
  `replay_applied_from_events`; the resume chain is followed by the existing helper.
- **Honesty of the verdict**: `external_anchor: absent` always (a bundle checkpoint is a same-store mint);
  `supported_checks` and `unsupported_checks` are listed in the result so the cockpit can say what was and was not
  established (no independent checkpoint HMAC, no operator-store correspondence, no full receipt/resource-table
  verification). `chain_consistent` is true only with a consistent chain, no failures, events present and a valid
  manifest.
- **Measured** at `94442bb` from a clean archive: `uv run --locked ruff check` on the reader and its tests: All checks
  passed; `tests/unit/test_replay_export.py`: JUnit tests=13 passed=13 failed=0 skipped=0; the eight `inspect_bundle` controls cover the baseline, empty evidence, emptied inventory, unbound
  manifest, non-finite payload, duplicate key, symlinked events and a checksum mismatch.

## Nits (not blocking; 3/3's call)

- `ok = chain_ok and not recorded and events and manifest is not None` is boolean only by evaluation order
  (`events` is a list); `bool(...)` would make the serialized `chain_consistent` type-safe by construction.
- `docs/BUNDLE_REPLAY.md` lists six supported checks; the code names nine (`manifest_binds_genesis`,
  `regular_files_only`, `nonempty_evidence` were added at 71781c3). The result dict is the authority; the doc lags.
- `os.read(fd, size + 1)` in one call is fine under the 8 MiB bound; a read loop would remove the assumption.

## What it does not do

- No import into the operator store, no listing of imported evidence beside stored runs, no authority; the seam
  and the cockpit label the result `replay`, never a stored run.

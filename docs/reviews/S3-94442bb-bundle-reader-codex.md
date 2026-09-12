# Seat 2/3 review — 94442bb

ACCEPT 94442bb482aaf6649bc93fe111d08aecf7883e8c. Exact isolated archive:
593 tests passed, zero failed/skipped; Ruff src/tests clean. JUnit
/private/tmp/astra-bundle-94442bb.xml.

Re-ran the original empty bundle, empty inventory, manifest/run mismatch and
symlink cases, plus nonfinite payload, duplicate event key and malformed resource
controls on real exported scripted evidence. Every corrupt variant reports
failed; the original valid export reports a consistent chain with absent anchor.
The findings in #28443 and #28455 are closed. Reads use a closed inventory,
regular files, explicit byte/event limits and captured bytes for hash and parse.
Manifest provenance binds to genesis; strict JSON rejects ambiguous/nonfinite data.
No operator store or provider is opened.

Limits remain explicit: this is reconstruction and checksum/chain inspection,
not independent authenticity, full receipt/resource-table verification or proof
of correspondence with the operator store. The cockpit must preserve these limits.

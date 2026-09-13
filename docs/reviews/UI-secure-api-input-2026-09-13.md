# Secure API input — assistant implementation review, 2026-09-13

Review kind: SELF-REVIEW by the continuation assistant, with assistant agents
for UI, backend and adversarial tests. No independent acceptance verdict or
matrix promotion. Base `0af7935fac47ea1751ba9e8916421caab37ae508`; source is the
commit introducing this file, plus any follow-up explicitly named in the final
receipt. Authority and interface amendment: ADR-022.

## Result and checks

- `tests/web/test_provider_credentials.py`: 28 tests exercise authentication,
  exact Host/Origin and CSRF, strict payloads, secret-bearing field names,
  malformed/duplicate/deep/oversized JSON, query refusal, redacted error paths,
  save/status/clear/logout, and an actual preview-bound hosted runtime through
  MockTransport with no key in its records, files or export. Save/clear contact
  no provider. Deeply nested JSON now receives the same generic parse failure.
- `tests/providers/test_credentials.py`: the service override is isolated from
  environment, other service instances and ambient contexts; request snapshots
  remain stable across concurrency, worker-thread health and key rotation;
  providers keep captured credentials; payload/store repr is redacted; empty,
  oversized, non-string and whitespace/control input is rejected without input
  details. New service construction has no entered credential.
- `tests/adversarial/test_credential_override_evidence.py`: 10 combinations of
  raw/Unicode-escaped keys in statements, reasoning, unexpected field names,
  action argument lists and errors are refused before action/effect. Scans cover
  service results, manifest, events, receipts, files, export and captured logs;
  no second model call occurs and the environment fallback remains unchanged.
- `tests/browser/credentials.cjs`: 23 focused checks passed. Masked input clears
  on submit, Escape, native close, pagehide, sign-out and expired authentication;
  focus returns to the opener. Only allowlisted status fields are rendered,
  including on reflected-error and lost-response simulations. No local/session
  storage or run/evidence mutation is introduced; saving does not start a catalog
  or paid request. Desktop/mobile/pending screenshots were inspected, with blank
  input fields. The dialog reports its memory lifetime and forget behavior.
  A catalog response started before a key change cannot restore stale choices.
  The final mobile check also covers long recorded-outcome labels behind the
  dialog. The existing friction test passed 23 checks, and the full browser
  harness passed all five reviews/lifecycle/bundles/comparison/studies flags.

## Finding fixed before integration

The adversarial pass found that the inherited `_contains_secret` depth check
silently skipped a valid action's nested list item. A synthetic escaped key
could reach a report write and the following model context. The new integration
test initially measured 9 passed / 1 failed; after the scanner fix, all 10 pass
and the combined hosted adversarial suite measures 39 passed. The fix separates
structural traversal from nested-string decoding and fails closed when bounded
inspection cannot finish. An incomplete scan has its own usage counter rather
than being labeled a proven credential reflection. Frozen ModelResponse errors
are unchanged. No real credential or live provider was used to reproduce it.

## Limits and final measurement

Memory storage is not persistent keychain storage or memory zeroization. The
existing loopback/browser trust boundary applies. The scanner's exact-match and
JSON-escape coverage and bounds are stated in ADR-022; arbitrary transformed or
split secrets are not covered by these tests. Entering a key confirms local
availability, not provider validity or billing permission.

The final clean-checkout suite, browser reruns and integrated source identity
belong to `docs/receipts/S7-secure-api-input.json` and the append-only tip log.
Temporary browser artifacts are in `/private/tmp/peb-credentials-browser-results/`;
the checked-in assertions are the reproducible evidence, not an externally
durable claim about those local screenshots.

# Hosted provider adversarial review — changes requested

Seat 2/3, 2026-09-11. Tested main20a0c5b, containing provider0079a37.
27 mocked controls: **21 passed, 6 failed**, no paid request or real credential.
Tests: `tests/adversarial/test_hosted_provider_boundary.py`.

## P1: credential echoed by upstream becomes exported evidence

An upstream completion echoes its received Authorization credential inside the
content. Both finish_reason=stop and length place the exact synthetic key in
model_response events and exported events.jsonl. Normal prompt omission and
repr masking do not cover response reflection. Check incoming content before it
crosses the credential-holding adapter into ModelResponse. Record a typed failure
or explicit redaction marker without the secret, and never treat redacted text
as an unchanged subject decision. Cover probe catalog/model metadata too.

## P2: malformed JSON shapes escape typed failure handling

GET /models with data=null or data=42 raises TypeError. A completion HTTP400 with
JSON [] or null raises AttributeError in _error_message. Validate shapes before
iteration/access and return bounded typed errors without reflecting bodies.

## Passing controls and limits

301/302/303/307/308 for probe and generate never follow redirects: exactly one
request to api.deepseek.com. Nine error-status cases discard echoed credentials
and issue one request, with no retry/fallback. Four malformed-catalog cases and
two malformed-error cases distinguish accepted handling from the failures above.
The tests use random synthetic credentials, mock transports and temporary state.
This is a provider review finding; the existing owner-held paid smoke is not run
or independently authorized here. Seat 1/3 owns provider fixes.

JUnit `/private/tmp/astra-provider-adversarial.xml` SHA-256:
`4ae3aa32fddfdac5cdb8d7518761a0ba82eb6c6f8f3f626bfdbe021086141b91`.

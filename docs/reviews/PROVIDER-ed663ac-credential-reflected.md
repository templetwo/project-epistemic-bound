# Review — DeepSeek credential-reflected + typed failures at ed663ac (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, provider-boundary owner.  
**Reviewed:** `ed663ac593144265e385bedf379e90f2334cdfc7` on `build/claude-core`  
**Predecessor smoke hash:** `0079a37` (ACCEPTed #27878).  
**Verdict:** **ACCEPT.** The smoke's reviewed commit may move from `0079a37` to `ed663ac` (or its `--no-ff` merge).

## Q1 — refuse the whole body on an exact-key match?

**Yes. That is the right first boundary.**

2/3's control was an exact Authorization credential in a completion or error body, then persisted into `model_response` and the export. Any field taken from that body can carry the key (content, resolved model id, catalog ids, error text). Scanning the **raw** bytes **before** parse, **any HTTP status**, and returning `content=""`, `model_resolved=None`, no catalog, typed `credential_reflected` is the minimum that closes the leak without putting the key into the record.

Exact-string is the honest cut. Fuzzy/partial/escaped/base64/split reflections are out of scope and **stated as such** in the ADR-017 addendum. Widening the matcher would false-fire (short keys, JSON punctuation). Residual encodings stay a named limit, not a CHANGES for this smoke.

The empty-key path does not scan (`if self._key and …`). Generate already returns `key_absent` before POST. Probe is the same.

Runtime already skips `parse_decision` when `error is not None` (finding (e) closed on this path). Truncated-but-clean bodies still keep content with `error=truncated`; a truncated body that contains the key is refused whole instead — correct, because keeping truncated content was the P1.

## Q2 — does the usage counter give enough visibility?

**Yes, for the smoke and for export forensics.**

`usage_report()["credential_reflected"]` is a count. Generate: `requests_attempted=1`, `responses_received=0`, `credential_reflected=1` (sent, body arrived, refused, not treated as usage-bearing). Probe reflections increment the same counter without `requests_attempted` — probe is not a billed generate; still visible.

Durable record: `ModelResponse.error == credential_reflected` lands on `model_response` with empty content. `provider_usage` is copied onto the run summary (`bootstrap.py`). The operator sees the count on the summary and the typed error on the event/export. Do not collapse this to zero; do not require a dollar rate for a leak count.

## P2 typed failures

`/models` `data` not a list → `transport`. Error bodies of any shape → string, never exception. Completion choice/message not objects → `transport`. **Pass.**

## Not this seat

`run.preview` is 1/3's service seam for 2/3's cockpit. No objection. Adversarial suite remains 2/3's.

No `bind_grants`. No paid smoke from this seat.

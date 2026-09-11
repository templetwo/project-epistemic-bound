# Review — DeepSeek correction pass 0079a37 (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `0079a37f30d3d1b5cc99acfd5085fdea4cb74721`  
**Verdict:** **ACCEPT** for PROVIDER-01/02 on this hosted path. Adversarial key-leakage tests remain 2/3.

## What holds

- Credential destination pinned to `APPROVED_HOSTS = {api.deepseek.com}`; non-https, userinfo, and other hosts refused at construct.
- `follow_redirects=False`; generate treats 3xx as `transport` / redirect refused. Key is only the Authorization header.
- Key is not a dataclass field; `repr` is present/absent; `_err` does **not** put HTTP bodies in `ModelResponse.content` (empty content, closed error code). Truncated keeps content with `error=truncated`.
- Runtime at this hash: `if response.error is not None` does not `parse_decision` (closes 3/3 finding (e) on this path).
- `thinking.type=disabled` sent; effective setting from `reasoning_content` presence, recorded on `usage_report`.
- Usage: `requests_attempted` / `responses_received` / with/without usage / `usage_fields_missing`; None not 0; `refused_before_send` for `input_limit_exceeded` before POST.
- Distinct codes; no fallback; no prompt rewrite to satisfy JSON mode.

## Notes, not CHANGES

- `_err(..., detail=)` discards detail — correct for the frozen record.
- Probe GET `/models` still sends the Authorization header to the approved host only.
- 2/3 owns making the key appear in events/export/repr/redirects as failing tests.

# Review — e823768 thinking ON, reasoning retained (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, provider-boundary owner.  
**Reviewed:** `e82376835dd608bbfa4a5f09b6919ca8e9107728` on `build/claude-core` (parent `2f64774`).  
**Verdict:** **ACCEPT.** This hash may become the smoke's reviewed unit (with 2/3's word on 2f64774+e823768 together). Paid smoke still Anthony.

Anthony, 2026-09-11: DeepSeek cost is not a constraint; capability rides on thinking. Locked here: never reduce calls, tokens, samples or thinking to save DeepSeek spend.

## Contract: `ModelResponse.reasoning`

Additive optional `str | None = None`. Ollama and error paths omit it (None). Schema regenerated. **Pass.** Not a silent required-field break of S1 freeze.

## Adapter: retain + scan, never parse as a decision

`reasoning_content` kept only when a non-empty str; otherwise None. Effective thinking is read from whether reasoning was present. Truncated completions keep reasoning beside content; `_err` (including `credential_reflected`) leaves reasoning None and content empty.

The credential walk is the whole `r.json()` (953921e). `reasoning_content` is a message string, so a key echoed there refuses the whole body — tested. Runtime still `parse_decision(response.content)` only, and skips parse when `error is not None`. The `model_response` event stores both `content` and `reasoning`. **Pass.**

`usage_report()["reasoning_tokens"]`: from `completion_tokens_details` when reported; stays None if never reported; never invented as 0. Reasoning tokens count against `max_output_tokens` (DeepSeek's completion budget) — stated in dry-run scope. **Pass.**

## Pin honoured on reopen

Create stores `settings.thinking` via `_provider_settings`. `_reopen_model_run` reads that pin and builds the provider with it. Default for new compose is `enabled`. CLI `--thinking {enabled,disabled}` default enabled. **Pass.**

**Note, not CHANGES:** if `settings.thinking` is missing (a DeepSeek run created before this pin), reopen defaults to `enabled`. Historical adapter default was disabled. No completed DeepSeek smoke exists. If any such run is reopened, 1/3 should refuse or honour `disabled` rather than silently flip. New creates always pin.

## Not this seat

Cockpit `--thinking` bind is 2/3. Preview token binding when thinking is explicit is 2/3. No paid request from this seat.

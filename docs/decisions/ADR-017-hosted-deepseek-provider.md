# ADR-017 — DeepSeek as an OPTIONAL hosted subject provider beside Ollama (never replacing it)

- Date: 2026-09-11, ~16:1x EDT (measured). Author: seat 1/3. Status: accepted on the lane; 3/3 reviews the
  provider boundary, 2/3 the acceptance tests, at the named commit.
- Direction, verbatim (Anthony, in seat 1/3's window): "add DeepSeek as an optional hosted subject provider,
  alongside—not replacing—Ollama. Keep the builders separate and reuse the existing runtime, decision parser,
  permission boundary, synthetic executor, and recorder. Keep Ollama's loopback restriction intact. Give DeepSeek its
  own explicit HTTPS endpoint, model selection, and locally supplied DEEPSEEK_API_KEY. Never include the key in
  prompts, receipts, exports, or committed files. Build and test the adapter with mocked responses first. Handle
  authentication errors, rate limits, timeouts, malformed/truncated output, and unavailable models explicitly,
  without automatic fallback. For the first live smoke test, propose deepseek-flash with the baseline profile. Show
  me the outbound-data scope and maximum call/token budget before any paid request. Record the actual model
  identifiers and settings, then verify and export the run whatever its outcome."

## Frozen-contract amendments (additive)

- `ProviderKind` += `deepseek`.
- `ModelResponse.error` += `key_absent`, `auth_error`, `insufficient_balance`, `rate_limited`, `server_error`,
  `bad_request` (distinct outcomes; none is a fallback trigger). Schemas regenerated (`docs/schemas/`).
- The Ollama loopback rule, the scripted provider, the parser, the monitor, the executor and the recorder are
  untouched. `Limits.max_output_tokens` (already in the contract) is the per-call output cap for both providers.

## The adapter (`src/peb/providers/deepseek.py`)

- Explicit `https://` endpoint (default `https://api.deepseek.com`; `PEB_DEEPSEEK_ENDPOINT` overrides); `http://`
  or a URL with userinfo is refused. `trust_env=False`: no inherited proxies.
- Explicit model id. `probe()` = `GET /models`; an unlisted id is `unknown_model` with the list returned; the run
  refuses to start. Never a default model, never a pull, never a substitution.
- Key: read only from the `DEEPSEEK_API_KEY` environment variable (the NAME is configurable and recorded; the VALUE
  is not a config field, not a dataclass field, masked in `repr`, sent only as the `Authorization` header). Tests
  scan the summary, every event, receipt, manifest and an export bundle for the key and for "Bearer".
- `generate()` = `POST /chat/completions`, `stream:false`, `temperature 0`, `max_tokens = Limits.max_output_tokens`,
  `response_format {"type": "json_object"}`. DeepSeek JSON mode requires the word "json" in the prompt; the adapter
  refuses (`unsupported_setting`) rather than editing the subject's prompt.
- Outcomes, each distinct and terminal for the run (the runtime records `provider_error:<code>` and stops):
  `key_absent`, `auth_error` (401/403), `insufficient_balance` (402), `rate_limited` (429), `unknown_model`,
  `bad_request`, `server_error` (5xx), `timeout`, `server_unreachable`, `transport` (malformed body),
  `truncated` (finish_reason `length`: bytes kept, never parsed), `model_id_mismatch`. Exactly one request per
  call; no retry inside the adapter.
- Usage: prompt/completion tokens and prompt-cache hit/miss tokens when returned, `None` when not (never 0);
  totals in the run summary as `provider_usage` (§21: report cache usage and missing fields; no price asserted).

## The pre-approval gate (`peb run --provider deepseek … --dry-run`)

`bootstrap.outbound_scope(...)` composes the run in a temporary state root with a provider stand-in that raises if
touched, renders the step-0 messages with the same allowlisted context builder, and reports: endpoint host and
scheme, model, arm, per-role character counts, a chars/4 token ESTIMATE, what grows per step, what is never
sent (private oracle, keys, other runs, builder transcripts, evaluator), and the budget (max calls, max output
tokens per call and total, a prompt-token lower bound, timeout). No network, no state change. The paid smoke
runs only after Anthony has seen this report and said so.

## Manifest settings pinned for a hosted run

`provider_endpoint_host`, `response_format`, `temperature`, `max_output_tokens`, `request_timeout_s`,
`max_model_calls`, `api_key_env` (the variable name). The resolved model id is recorded per response.

## Consequences

- PROVIDER-01/02 extend to the hosted provider: distinct failures, explicit model, bounded calls, no download,
  no fallback; the endpoint policy is "loopback only" for Ollama and "explicit https only" for DeepSeek.
- The service seam's `run.start` accepts `provider: "ollama"|"deepseek"` and `max_output_tokens`; the web layer
  must show the dry-run scope before offering a paid start (UI rule for seat 2/3).
- `docs/HANDOFF.md` "Which model was actually called" changes as smokes are run; see `docs/evidence/live-01/`.

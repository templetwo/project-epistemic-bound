# ADR-022 — secure provider input for the running workroom

Date: 2026-09-13. Status: implemented at Anthony's explicit request, "add a
\"secure api input\" window". This supersedes ADR-017's environment-only key
entry rule and ADR-021's statement that no browser API-key field is introduced.
It does not authorize inference, alter subject grants, change frozen contracts
or resolve ADR-020's independent-review question.

## Behavior

An authenticated operator can open **Secure API input**, enter a DeepSeek key,
and choose **Use key for this server**. The input is masked. The application
does not put the key in localStorage, sessionStorage, a URL, a run selection,
preview token, model context, event, receipt or export. It clears the field on
submission, dismissal, sign-out and page departure. The dialog does not reveal
the stored value; it reads back only whether a credential is available and
where it came from.

The key is kept in memory by that WorkroomService instance. A service request
captures its credential context before invoking runtime or readiness code;
providers retain the selected key while a call is in progress. Other service
instances and unrelated CLI commands do not acquire the override. This does
not write to `os.environ`, a credential file or the operator database. New
requests prefer the entered key; without one they retain the existing
`DEEPSEEK_API_KEY` environment fallback.

**Forget entered key** removes the memory override. If the server was launched
with an environment key, that fallback remains and the status says so. A server
restart discards entered keys. Operator sign-out closes access to the control
but does not cancel a running provider call or erase the server credential;
the explicit forget control handles removal.

Saving, forgetting and checking credential presence contact no provider and
create no run. The existing **Check the hosted catalog** control performs the
separate catalog read. The hosted scope preview and explicit authorization
remain required before a paid run.

## Boundary and limits

The three fixed credential routes require the existing operator session. POST
also requires the exact loopback Host/Origin and CSRF token. Responses have the
same no-store and content-security headers as the workroom. Credential requests
accept no query parameters. Their body limit is 4 KiB, and an entered key must
be a nonempty, whitespace-free printable ASCII string of at most 512 characters.
Malformed, excessive, deeply nested and schema-invalid requests return generic
errors without reflecting submitted values or field names. The parsed payload
reference is released after use. Python and browser string memory are not
guaranteed to be zeroized.

This uses the existing loopback HTTP transport and trust model; it is not a
remote credential service, encrypted vault or protection against a privileged
process, malicious browser extension or developer-tools inspection on the same
machine. Autocomplete is disabled by the application, but a browser or password
manager can apply its own policy. Do not describe the UI as hardware-backed
storage or claim that masking encrypts the key. The only credential-bearing
external destination remains the pinned HTTPS DeepSeek host, with redirects
and credential-reflecting provider responses refused by the existing adapter.

An implementation review reproduced an inherited scanner defect: structural
nesting used up the old depth allowance before a Unicode-escaped key in a valid
action's `evidence_refs` list could be examined. The scanner now traverses JSON
structure iteratively and applies its depth budget only to JSON documents
encoded inside strings. It refuses the whole body when inspection exceeds
4 MiB of response bytes, 8 nested decoding layers, 100,000 values or 4,194,304
cumulative characters in strings submitted for JSON decoding.
The adapter reports an incomplete catalog scan explicitly; a completion uses
the existing frozen `transport` error and increments `credential_scan_refused`.
It does not falsely increment `credential_reflected` without finding a match.
Tests establish whole-key and JSON-escaped reflection refusal, not protection
against every possible partial, split or transformed upstream encoding.

## Interface amendment and evidence

INTERFACES §18 documents the additive service operations and fixed HTTP routes.
The key payload is a separate operator channel; it is never part of a frozen
model contract. Credential payload validation and transport error handling
both suppress input-bearing details, including a secret supplied as a JSON key.

Named checks live in `tests/web/test_provider_credentials.py`,
`tests/providers/test_credentials.py`,
`tests/adversarial/test_credential_override_evidence.py` and
`tests/browser/credentials.cjs`. They use synthetic keys and mocked provider
responses. Measurements belong to the dated assistant review and receipt;
they are implementation checks, not independent acceptance or a paid model
observation.

References used during implementation:
[OWASP logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
for excluding secrets from logs, and [MDN's native dialog reference](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog)
for modal focus and dismissal behavior.

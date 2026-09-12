# ADR-019 — A terminal cockpit as a second presentation over the same operator boundary

**Status:** accepted for slice 1 (transport, sanitizer, state model) on 2026-09-12; the terminal application and the
`peb tui` command follow in slice 2 with an addendum naming the rendering library.
**Context:** Anthony, 2026-09-12 00:3x EDT: "i would like a tui i can use." An outside design document
(`docs/design/peb_cockpit_tui_design.md`, received the same night) was used as input where it fits the
boundaries on `main`; it is not a specification ("dont feel obligated to use the spec 'exactly'").

## Decisions

1. **One boundary, two presentations.** The terminal cockpit is an authenticated client of the EXISTING loopback
   web seam (`peb.web`): the same `POST /api/auth/login` session cookie and CSRF token, the same canonical
   `Origin` on every mutation, the same fixed `/api/...` routes and typed error envelope, the same one-use hosted
   preview token before a paid start. Nothing under `peb.tui` imports the writable repository, a provider, the
   reference monitor or the executor. Seat 2/3's read (#28438): the seam stands as the operator gateway; moving
   the hosted-preview policy elsewhere is unnecessary for the read-only milestone.
2. **"Real time" is observation of committed evidence.** Cursor polling over the seam's event pages (≈0.75 s on
   an active selected run, 2 s when paused or waiting for review, 5 s when terminal), immediate refresh after an
   operator action, bounded exponential backoff on read failures. No provider token streaming: the providers run
   with `stream: false`, and a half-streamed decision is not a recorded decision.
3. **Evidence honesty rules, each with a test** (`tests/tui/test_model.py`): event `seq` orders the view; a page that
   does not continue the cached head (cursor, previous hash, order) drops the run's events and refetches from
   zero — never stitched; a response for an earlier selection is discarded (generation counter); verification is
   pinned to the head it verified and shown STALE when the head moves — a newer head never inherits an older
   badge, and "chain consistent, external anchor absent" is shown as exactly that, never as "verified"; a run
   with no `model_request` is "recorded, not started" even though the store's row says `running`; unknown usage
   stays unknown (never 0); controls are offered only against a projection refreshed within 2 s.
4. **Zero automatic mutation retries.** A mutation whose answer never came back is `UncertainOutcome`: the workroom
   may have applied it; the cockpit refetches inventory and evidence before offering the action again. Reads may
   retry with backoff. (`tests/tui/test_http_transport.py`: exactly one attempt on a timeout.)
5. **Untrusted text never controls the terminal.** Every displayed string (model content, reasoning, task text,
   commitment text, resource values, review notes, provider errors) passes `peb.tui.sanitize.display`: C0/C1
   controls and DEL become visible control pictures, invisible Unicode controls and separators are made visible,
   output is length-bounded. The design document's adversarial string (OSC 52 clipboard write + screen clear +
   "fake verified") renders as visible text; kept as a test verbatim.
6. **The secret is never a command-line argument and never printed.** Slice 2's `peb tui` prompts without echo or
   reads the operator secret from the protected state root when it starts the workroom itself.

## Consequences

- No new service operation for this slice; the seam's routes are sufficient for read-only parity and the
  existing controls. `events.since` (a read-only, head-carrying page operation) and a commit-notification
  stream are deferred until polling is measured to be insufficient.
- The web layer gains a second client; its tests already cover the properties the cockpit relies on (host/origin
  checks, CSRF, session expiry, the preview token). The transport's tests run against the real FastAPI app in
  process on a temporary state root.
- The rendering library is chosen in slice 2 after the transport, state and sanitizer exist; the choice must not
  alter any workroom semantics.

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

## Addendum 2026-09-12 — slice 2: the application, `peb tui`, and the rendering library

`peb tui --attach URL | --serve [--host --port]` (recorded in the §20 command test as an ADR-019 addition). `--serve`
starts the EXISTING `peb serve` as a child process of this interpreter and attaches; there is no second runtime. The
secret is read from the protected state root or prompted without echo, consumed by the first sign-in inside the
app's own event loop, and dropped. Rendering library: **Textual 8.2.8** (new dependency `textual>=8.2.8`, with
`rich`), chosen after the transport, state and sanitizer existed, for its headless test pilot (`App.run_test()`):
every screen rule is asserted through simulated key presses on a fake transport that records each call, so
"viewing writes nothing", "every control maps to one closed operation and refetches", "the badge goes stale on
screen when the head moves", "a chain gap resyncs" and "hostile text is inert on screen" are tests, not claims.
The choice alters no workroom semantics; the transport and the state model are library-neutral.
Two transport corrections from seat 2/3's review of slice 1 (#28469) are in this slice: any connection loss after a
mutation was sent is an unknown outcome (not only a timeout), and a 200 with a body that is not a JSON object is a
typed error for a read and an unknown outcome for a mutation, never an empty success.

## Addendum 2026-09-12 — slice 2 corrections from seat 2/3's review (#28502, #28511; 3/3 concurred #28505)

1. **Child state root.** `--serve` forwards the RESOLVED state root to the child both as `--state-root` and as
   `PEB_STATE_ROOT`; an explicit CLI root overrides anything inherited (tested with a fake process and socket).
2. **Quit is detach, never stop.** No inventory read is a shutdown interlock (another client may start a run after any
   read; the cockpit may quit before its first inventory), so a workroom started by `--serve` is always left running
   and reported (origin, pid, runs seen in flight or "unconfirmed", re-attach and stop commands). Only a child that
   fails to start listening is cleaned up, by the spawner that still owns it.
3. **Literal rendering.** Textual and Rich interpret markup by default; the sanitizer does not strip brackets. Every
   untrusted surface is a `Content` object on a widget created with `markup=False`, and table cells are `Text` objects;
   the test reads the widgets' rendered content (plain text equal to the tags, zero spans), not the pre-render string.
4. **Evidence binding.** A page is appended only as an exact continuation: cursor at the cached end, no shrinking
   total, contiguous `seq`, every `prev_hash` link inside and across the page boundary, a genesis with no previous hash
   at cursor 0, the run's own identity. A verification badge binds to the head the verifier reports having covered
   (`checked_events` equal to the cached count); any other result is UNBOUND on screen and in the alerts.

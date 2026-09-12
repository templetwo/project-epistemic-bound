# The terminal cockpit — `peb tui`

A second presentation over the same operator boundary as the browser workroom (ADR-019). It is an
authenticated client of the loopback web seam: the same session cookie, CSRF token, fixed routes, typed errors
and hosted preview rule. It never touches the store, a provider, the reference monitor or the executor, and
viewing it writes nothing.

## Run it

```bash
uv run --locked peb tui --serve                      # start the existing workroom (peb serve) as a child, then attach
uv run --locked peb tui --attach http://127.0.0.1:8787   # join a workroom that is already serving
```

The operator secret is read from `operator.secret` in the workroom's state root when it is there; otherwise it
is prompted for without echo. It is never a command-line option and never printed. `q` leaves the cockpit; the
run keeps going (and the child workroom is stopped only in `--serve` mode).

## What you see

- **Status line**: storage and local-provider readiness, run count, view freshness (`LIVE` ≤1 s, `FRESH` ≤5 s,
  `STALE`, `OFFLINE`), the clock (`z` toggles local/UTC), the workroom origin.
- **Runs** (left): the inventory as `runs.list` returns it — id, stored status, mode, created time. Moving the
  cursor selects a run; everything to the right belongs to that run.
- **Overview**: stored status **and** activity kept apart (`RECORDED — NOT STARTED` until a `model_request` is
  recorded, `MODEL WAIT`, `RUNNING`, `PAUSED`, `WAITING FOR REVIEW`, terminal states), provider, requested and
  resolved model, `artifact digest — not recorded` (no digest is recorded today; none is invented), profile and
  arm, task, frame, calls used / max, token totals summed from recorded responses (`—` when unknown, never 0).
- **Events**: the recorded chain in `seq` order — time, type, actor, hash. New events are appended as they
  are committed; a page that does not continue the cached head triggers a full resync (logged), never stitching.
- **Permissions**: the grants in the projection — tool, ALLOWED / APPROVAL, revoked, policy version. Distinct
  from commitments by design: a commitment grants no permission.
- **Commitments**, **Reviews**: the projections, with held proposals marked.
- **Evidence**: head seq, event count and head hash; the verification badge **pinned to the head it verified**
  (`STALE, verify again` when the head moved); anchor provenance. "chain consistent, external anchor absent" is
  shown as exactly that, never as "verified".
- **Alerts**: derived from the view (open reviews, failed verification, a moved head, a stale view, a provider
  problem). They are not evidence and are not written anywhere.
- **Operations log**: the cockpit's own requests and refusals (sanitized), bounded.

## Keys

| Key | Operation | Notes |
|---|---|---|
| `g` | refresh now | reads only |
| `n` | `demo.run` | scripted control: `case [frame]` |
| `v` | `evidence.verify` | explicit; the badge is pinned to this head |
| `e` | `evidence.export` | absolute output directory; local only |
| `h` / `u` | `run.pause` / `run.resume` | |
| `s` / `b` | `run.step` / `run.begin` | local runs; the seam refuses hosted lifecycle without a preview |
| `x` | `run.cancel` | type the final 6 characters of the run id to confirm |
| `a` / `l` / `d` | `review.resolve` ack / allow / deny | the first open review of the selected run |
| `q` | leave the cockpit | the run keeps going |

Every mutation is one attempt. If the answer never comes back (timeout, reset, malformed reply) the log says
**RESULT UNKNOWN**, nothing is retried, and the cockpit refetches the inventory and the evidence before offering
the control again. Controls are offered only against a projection refreshed within the last two seconds.

## What it never does

Reads the API key or the environment; contacts Ollama or DeepSeek; imports the store; starts a hosted run
without the seam's one-use preview token; shows a fresh event as "verified"; shows an unknown token count or
digest as a value; stitches over a gap in the chain; retries a mutation; writes evidence by being open.

## Tests

`tests/tui/`: sanitizer (the design document's adversarial string, C0/C1/DEL, hidden Unicode controls), the
transport against the real FastAPI seam in process (sign-in, CSRF, routes, pagination, typed errors, uncertain
outcomes, malformed replies), the state rules (continuity, generation guard, badge staleness, recorded ≠ started,
unknown usage, freshness, backoff), and the app headless through Textual's pilot (viewing writes nothing,
selection and rendering, badge staleness on screen, resync on a chain gap, every control's operation and
refetch, the typed cancel confirmation, hostile text inert).

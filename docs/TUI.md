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
is prompted for without echo. It is never a command-line option and never printed. `--serve` forwards the resolved
state root to the child (an explicit `--state-root` wins over an inherited `PEB_STATE_ROOT`).

## Attach, detach, stop

- **Attach**: `--attach URL` joins a workroom that is already serving (loopback only). The operator secret is read
  from the cockpit's configured state root, so name the SAME root the workroom serves
  (`peb --state-root ROOT tui --attach URL`); with a different root the wrong secret is offered and sign-in fails.
  `--serve` starts a workroom as a child of this process on the resolved state root and attaches to it — an
  alternative to `serve` + `--attach`, not an addition (one workroom per port).
- **Detach**: `q` leaves the cockpit and **detaches**. Runs keep going, and a workroom started by `--serve` keeps
  serving. The cockpit prints the workroom's origin, pid, the runs it saw in flight at quit (or that it could not read
  them), how to re-attach and how to stop it. Nothing is terminated by the cockpit closing: no inventory read can be a
  shutdown interlock (another client may start a run after any read), so the ownership contract is explicit.
- **Stop**: you stop the workroom when you are done with it (`kill <pid>`, printed at quit). The only automatic
  clean-up is a child that fails to start listening.

## What you see

- **Status line**: storage and local-provider readiness, run count, view freshness (`LIVE` ≤1 s, `FRESH` ≤5 s,
  `STALE`, `OFFLINE`), the clock (`z` toggles local/UTC), the workroom origin.
- **Runs** (left): the inventory as `runs.list` returns it — id, stored status, mode, created time. Moving the
  cursor selects a run; everything to the right belongs to that run.
- **Overview**: stored status **and** activity kept apart. Every stored status maps explicitly: `created` and a
  `running` row with no `model_request` yet are `RECORDED — NOT STARTED`; `running` is `MODEL WAIT` or `RUNNING`;
  `waiting_review`, `paused`, `completed`, `declined`, `failed`, `cancelled`, `interrupted` each show as themselves;
  anything else shows as `UNKNOWN STATUS`, never as running. Then provider, requested and resolved model,
  `artifact digest — not recorded` (no digest is recorded today; none is invented), profile and arm, task, frame,
  calls used / max, and the **usage line**: for prompt, completion and reasoning tokens, the sum of what provider
  responses reported **with its coverage** — `prompt 100 PARTIAL (reported by 1 of 2 responses; 1 unreported)`,
  `completion — (unreported by 2 of 2 responses)`, `prompt 1 (reported by all 1 responses)` — always ending
  `reported by provider responses; not a bill`. A partial sum is never shown as a total; unknown is never shown as 0.
- **Events**: the recorded chain in `seq` order — time, type, actor, hash. New events are appended as they
  are committed; a page that does not continue the cached head triggers a full resync (logged), never stitching.
  Moving the cursor here drives the **Inspect** tab.
- **Inspect**: the recorded story of the highlighted event, linked by `proposal_id` (and by `step` for the
  decision) from the cached chain and the projection's grants only: the public **statement** (`decision_recorded`),
  what was **proposed** (tool, claimed grant, action digest — "a proposal is not an execution"), what was
  **declared before acting** (`preaction_declared`), the claimed grant's **actual authority** from the projection
  (tool, resources, approval requirement, revocation, public description — or "NOT in this run's projection"), the
  **gate's** decision(s) with reason and resolved grant ("an allow is not an execution"), and the **effect**: an
  `effect_observed` with its status and every resource's revision before → after, or `NO EFFECT RECORDED` when the
  proposal was denied, held, a read, or allowed but never executed. Review openings and resolutions for the proposal
  are listed. A `model_response` or `model_request` row shows only its recorded metadata (model resolved, finish
  reason, reported usage; message count and input hash): model content, retained reasoning and what the subject was
  sent are in the record and are **not** the inspector's feed (their display scope is reviewed separately); the
  private oracle and builder history are never in the projection at all.
- **Permissions**: the grants in the projection — tool, ALLOWED / APPROVAL, revoked, policy version. Distinct
  from commitments by design: a commitment grants no permission.
- **Commitments**, **Reviews**: the projections, with held proposals marked.
- **Evidence**: head seq, event count and head hash; the verification badge **bound to the head identity the
  verifier reported** (below); anchor provenance. "chain consistent, external anchor absent" is shown as exactly
  that, never as "verified".
- **Alerts**: derived from the view (open reviews, failed verification, a moved head, an unbound or wrong-run
  verification, a stale view, a provider problem). They are not evidence and are not written anywhere.
- **Operations log**: the cockpit's own requests and refusals (sanitized), bounded.

## Keys

| Key | Operation | Notes |
|---|---|---|
| `g` | refresh now | reads only |
| `n` | `demo.run` | scripted control: `case [frame]` |
| `v` | `evidence.verify` | explicit; the badge is bound to the head identity the verifier returns |
| `e` | `evidence.export` | absolute output directory; local only |
| `h` / `u` | `run.pause` / `run.resume` | |
| `s` / `b` | `run.step` / `run.begin` | local runs; the seam refuses hosted lifecycle without a preview |
| `x` | `run.cancel` | type the final 6 characters of the run id to confirm |
| `a` / `l` / `d` | `review.resolve` ack / allow / deny | opens the review chooser, then the confirmation (below) |
| `q` | leave the cockpit | detaches; runs and a started workroom keep going; the stop command is printed |

### Reviews: choose, see, confirm, send once

`a`, `l` and `d` never act on "the first open review". They open a chooser listing every open review of the
selected run (id, status, conflict, proposal, deadline; ↑/↓ then Enter; Escape cancels). The chosen review's
confirmation then shows its recorded context — the run and its current stored status and activity, the review's
status, conflict, deadline and whether its proposal is held, and the proposal's inspector story (statement, proposal,
declaration, the claimed grant's actual scope, the gate so far, the effect so far) — with the reminder that
acknowledgement grants no authority, allow re-gates the held proposal against current grants and state, deny records
the refusal, and the backend validates independently. `y` sends exactly that decision for exactly that review; `n`
or Escape cancels. Right before sending, the cockpit re-reads the run: if the review's status or the run's status
differs from what was shown, nothing is sent and the change is logged — the target is never silently switched. One
attempt, never retried.

### Verification: bound to what the verifier covered

`v` calls `evidence.verify`. The seam returns, beside the verification result, the head identity the verifier
actually covered (`verified_head`: run id, event count, head hash — computed from the store's chain right after the
verification, only when the count read back equals `checked_events`). The badge binds to **that** identity, never to
the view's own hash on the grounds that the counts matched:

- identity for this run, equal to the view's head → the verifier's summary as-is;
- identity for this run, same count but a **different hash** → the view was not the store's chain: the view is
  resynced from the genesis and the badge says so;
- the view's head moves afterwards → `STALE, verify again` (a newer head never inherits a badge);
- identity naming **another run**, or **no identity** at all → `UNBOUND`, with the reason, and an alert.

## Rules that are tests

Every mutation is one attempt. If the answer never comes back (timeout, reset, malformed reply) the log says
**RESULT UNKNOWN**, nothing is retried, and the cockpit refetches the inventory and the evidence before offering
the control again. Controls are offered only against a projection refreshed within the last two seconds.

Everything on screen is rendered **literally**: a bracketed tag in model text, a commitment or a review note is shown
as characters, never as styling or a terminal hyperlink. Events are accepted only as a contiguous, fully linked
continuation of what the cockpit already holds (every sequence number and every previous-hash link, the run's own
identity, no shrinking snapshot); anything else resyncs from the start.

## What it never does

Reads the API key or the environment; contacts Ollama or DeepSeek; imports the store; starts a hosted run
without the seam's one-use preview token; shows a fresh event as "verified"; binds a badge to a hash the verifier did
not report; shows an unknown or partial token count as a total, or any count as a bill; shows model content, retained
reasoning or the subject's input in the inspector; acts on a review the operator did not choose and confirm; stitches
over a gap in the chain; retries a mutation; writes evidence by being open.

## Tests

`tests/tui/`: sanitizer (the design document's adversarial string, C0/C1/DEL, hidden Unicode controls), the
transport against the real FastAPI seam in process (sign-in, CSRF, routes, pagination, typed errors, uncertain
outcomes, malformed replies), the state rules (continuity, generation guard, every stored status mapped, usage
coverage and the partial label, verification bound only to the verifier-reported identity — equal counts with a
different hash, a wrong-run answer, a missing identity, a head that advances — recorded ≠ started, freshness,
backoff, the inspector on authorized concealment versus a blocked boundary crossing versus an allow with no effect
with no model content shown), and the app headless through Textual's pilot (viewing writes nothing, selection and
rendering, badge staleness and resync on screen, resync on a chain gap, every control's operation and refetch, the
typed cancel confirmation, the review chooser with two open reviews sending only the chosen id, a review or run that
changes while the confirmation is open sending nothing, the inspector following the highlighted event, declined and
interrupted rendered distinctly, hostile text inert).

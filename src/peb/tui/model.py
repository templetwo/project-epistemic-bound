"""The cockpit's state, and the pure rules that keep it honest.

Rules (each has a test):
- `seq` orders events; a page that does not continue the cached (count, head hash) is a discontinuity → the run's
  events are dropped and refetched from cursor 0 (RESYNC), never stitched.
- A selection generation counter: a response that belongs to an earlier selection is discarded.
- Verification is an explicit act on a specific head. `VerificationBadge` carries the head IDENTITY the verifier
  reported (run, event count, head hash) — never a hash borrowed from the view because the counts matched (outside
  reviewer, pass 2: equal counts do not prove identical evidence). A result with no identity, or for another run, is
  UNBOUND. When the view's head moves the badge is STALE; when the view holds a different hash at the same seq the
  view is not the store's chain and is resynced. A consistent chain with no external anchor is shown as exactly that.
- Every stored status maps explicitly (`ACTIVITY`); an unknown status is shown as unknown, never as RUNNING.
- Usage is the sum of what provider responses REPORTED, shown with its coverage (how many responses reported it);
  a partial sum is labelled partial; nothing here is a bill.
- Freshness is measured from the last successful refresh of that surface; mutations are offered only when the
  target run's projection is fresh (≤ `MUTATION_FRESHNESS_S`).
- Recorded ≠ started: the store's row says `running` from genesis; a run with zero `model_request` events shows
  "recorded, not started".
- The event inspector (`inspect_event`) links what the record holds for one decision — public statement, proposed
  action, pre-action declaration, the claimed grant's actual scope, the gate's decision, the observed effect — and
  says plainly when a proposal or an allow produced no executed effect. It never shows model content or retained
  reasoning, the private oracle, or what the subject was sent.
- Alerts and the operations log are UI derivations; nothing here writes evidence.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any

from .sanitize import display
from .transport import EventPage

MUTATION_FRESHNESS_S = 2.0
STALE_AFTER_S = 5.0
ACTIVE_POLL_S, WAITING_POLL_S, IDLE_POLL_S = 0.75, 2.0, 5.0
BACKOFF_S = (0.75, 1.5, 3.0, 6.0, 8.0)
# Every RunStatus the runtime records (contracts.RunStatus), mapped explicitly. `canceled` is tolerated as the US
# spelling of the same terminal state. Anything else is UNKNOWN on screen — never RUNNING by fall-through.
TERMINAL = {"completed", "declined", "failed", "cancelled", "canceled", "interrupted"}
ACTIVITY = {
    "completed": "COMPLETED", "declined": "DECLINED", "failed": "FAILED", "cancelled": "CANCELLED",
    "canceled": "CANCELLED", "interrupted": "INTERRUPTED", "waiting_review": "WAITING FOR REVIEW", "paused": "PAUSED",
}
USAGE_FIELDS = (("prompt_tokens", "prompt"), ("completion_tokens", "completion"), ("reasoning_tokens", "reasoning"))
USAGE_NOTE = "reported by provider responses; not a bill"
OPEN_REVIEW = ("pending", "acknowledged")


@dataclass(frozen=True)
class Head:
    count: int
    hash: str | None

    @staticmethod
    def of(events: list[dict[str, Any]]) -> Head:
        return Head(len(events), events[-1].get("event_hash") if events else None)


@dataclass(frozen=True)
class VerificationBadge:
    head: Head              # the head identity the VERIFIER reported (hash None = it reported none we could bind)
    summary: str            # the verifier's own words, e.g. "chain_consistent; external_anchor_absent"
    chain_consistent: bool
    anchor: str             # anchor provenance as reported
    at: float               # monotonic time of the verification
    identity: str = "bound"  # bound | unbound | wrong_run | mismatch (what apply_verification concluded)

    def label(self, current: Head) -> str:
        base = self.summary
        if self.identity == "wrong_run":
            return f"{base} — UNBOUND: the verifier answered for ANOTHER run; verify again"
        if self.head.hash is None:
            covered = "an unknown number of" if self.head.count < 0 else str(self.head.count)
            return f"{base} — UNBOUND: the verifier reported no head identity ({covered} events covered); the view holds {current.count}; verify again"
        if current == self.head:
            return base
        if current.count == self.head.count:
            return (f"{base} — VERIFIED head hash differs from the view's at the same seq {self.head.count - 1}: the view was not "
                    "the store's chain; resynced, verify again")
        return f"{base} — VERIFIED AT head seq {self.head.count - 1}, head now seq {current.count - 1}: STALE, verify again"

    @property
    def bound(self) -> bool:
        return self.head.hash is not None and self.identity in ("bound", "mismatch")


@dataclass(frozen=True)
class RunView:
    run_id: str
    snapshot: dict[str, Any] | None = None       # the seam's run.get body, as received
    events: tuple[dict[str, Any], ...] = ()
    next_cursor: int | None = 0                  # None = end of the current snapshot
    refreshed_at: float | None = None
    verification: VerificationBadge | None = None
    resyncs: int = 0

    @property
    def head(self) -> Head:
        return Head.of(list(self.events))

    @property
    def status(self) -> str:
        return str(self.snapshot.get("status", "unknown")) if self.snapshot else "unknown"

    @property
    def started(self) -> bool:
        return any(e.get("event_type") == "model_request" for e in self.events)

    @property
    def activity(self) -> str:
        """What the run is doing, kept apart from the stored status. Every stored status is mapped explicitly."""
        if self.snapshot is None:
            return "loading"
        status = self.status
        if status in ACTIVITY:
            return ACTIVITY[status]
        if status == "created" or (status == "running" and not self.started):
            return "RECORDED — NOT STARTED"
        if status == "running":
            last = self.events[-1].get("event_type") if self.events else None
            return "MODEL WAIT" if last == "model_request" else "RUNNING"
        return f"UNKNOWN STATUS {display(status, one_line=True, max_chars=40)!r}"

    @property
    def model_calls(self) -> int:
        return sum(1 for e in self.events if e.get("event_type") == "model_request")

    @property
    def usage(self) -> dict[str, Any]:
        """Token totals from recorded model_response payloads WITH coverage: `responses` = responses recorded,
        `<field>` = the sum of the responses that reported it (None when none did), `<field>_reported` = how many
        did. A sum over fewer than all responses is partial and is shown so; unknown stays unknown, never zero."""
        responses = [e.get("payload") or {} for e in self.events if e.get("event_type") == "model_response"]
        out: dict[str, Any] = {"responses": len(responses)}
        for key, name in USAGE_FIELDS:
            values = [p.get(key) for p in responses]
            ints = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
            out[name] = sum(ints) if ints else None
            out[f"{name}_reported"] = len(ints)
        return out

    def open_reviews(self) -> list[dict[str, Any]]:
        return [r for r in ((self.snapshot or {}).get("reviews") or []) if r.get("status") in OPEN_REVIEW]

    def grants(self) -> list[dict[str, Any]]:
        return list(((self.snapshot or {}).get("run") or {}).get("grants") or [])

    def poll_interval(self) -> float:
        if self.status in TERMINAL:
            return IDLE_POLL_S
        if self.status in ("waiting_review", "paused"):
            return WAITING_POLL_S
        return ACTIVE_POLL_S


def format_usage(usage: dict[str, Any]) -> str:
    """One line: each field's reported subtotal with its coverage; partial and unknown are named, never totals."""
    n = usage.get("responses", 0)
    parts = []
    for _, name in USAGE_FIELDS:
        total, reported = usage.get(name), usage.get(f"{name}_reported", 0)
        if total is None:
            parts.append(f"{name} — (unreported by {n} of {n} responses)" if n else f"{name} — (no responses)")
        elif reported < n:
            parts.append(f"{name} {total} PARTIAL (reported by {reported} of {n} responses; {n - reported} unreported)")
        else:
            parts.append(f"{name} {total} (reported by all {n} responses)")
    return "tokens " + " · ".join(parts) + f" · {USAGE_NOTE}"


@dataclass(frozen=True)
class Alert:
    level: str  # critical | action | warning | info
    text: str
    run_id: str | None = None


# ----------------------------------------------------------------------------- the event inspector (pure)

_HIDDEN_PAYLOAD_KEYS = {"messages", "content", "reasoning"}  # what the subject was sent / said: not the inspector's feed


def _d(value: Any, n: int = 160) -> str:
    return display(value, one_line=True, max_chars=n)


def _rev_lines(before: Any, after: Any) -> list[str]:
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    return [f"    {_d(rid, 40)}: revision {_d(before.get(rid, '—'), 12)} → {_d(after.get(rid, '—'), 12)}"
            for rid in sorted(set(before) | set(after), key=str)]


def inspect_event(view: RunView, index: int) -> str:
    """The recorded story of ONE selected event, linked by `proposal_id` (and `step` for the decision), from the
    cached chain and the projection's grants only. A proposal is not an execution; an allow is not an execution;
    only an `effect_observed` with an applied status changed a resource. Never model content or retained reasoning,
    never the private oracle, never the subject's input."""
    events = list(view.events)
    if index < 0 or index >= len(events):
        return "select an event in the Events tab"
    ev = events[index]
    raw_payload = ev.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    kind = str(ev.get("event_type", "?"))
    lines = [f"EVENT seq {ev.get('seq')} · {_d(kind)} · actor {_d(ev.get('actor'))} · {_d(str(ev.get('ts', ''))[:19])} · hash {_d(ev.get('event_hash', '—'), 16)}"]
    if kind == "model_response":
        usage = ", ".join(f"{k} {_d(payload.get(k))}" for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens") if payload.get(k) is not None)
        lines.append(f"MODEL RESPONSE: model resolved {_d(payload.get('model_resolved', '—'))} · finish {_d(payload.get('finish_reason', '—'))}"
                     + (f" · {usage}" if usage else " · usage unreported"))
        lines.append("  content and retained reasoning are in the record; not shown here (their display scope is reviewed separately)")
    elif kind == "model_request":
        lines.append(f"MODEL REQUEST: step {_d(payload.get('step'))} · {_d(payload.get('message_count', '?'))} messages · input hash {_d(payload.get('input_hash', '—'), 16)}")
        lines.append("  what the subject was sent is in the record; not shown here")
    else:
        shown = {k: v for k, v in payload.items() if k not in _HIDDEN_PAYLOAD_KEYS and k not in ("before", "after", "declaration")}
        if shown:
            lines.append("PAYLOAD: " + " · ".join(f"{_d(k, 32)} {_d(v, 80)}" for k, v in sorted(shown.items(), key=lambda kv: str(kv[0]))))
    proposal_id = payload.get("proposal_id")
    step = payload.get("step")
    if proposal_id is None and kind == "decision_recorded" and step is not None:
        for other in events:
            op = other.get("payload") if isinstance(other.get("payload"), dict) else {}
            if other.get("event_type") == "action_proposed" and op.get("step") == step:
                proposal_id = op.get("proposal_id")
                break
    if proposal_id is None and step is None:
        return "\n".join(lines)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for other in events:
        op = other.get("payload") if isinstance(other.get("payload"), dict) else {}
        linked = (proposal_id is not None and op.get("proposal_id") == proposal_id) or \
                 (other.get("event_type") in ("decision_recorded", "decision_invalid") and step is not None and op.get("step") == step)
        if linked:
            by_type.setdefault(str(other.get("event_type")), []).append(op)
    lines.append("— the recorded story of this decision —")
    for d in by_type.get("decision_recorded", []):
        lines.append(f"STATEMENT (public, step {_d(d.get('step'))}): {_d(d.get('kind'), 20)} — {_d(d.get('statement', ''), 240)}")
    for d in by_type.get("decision_invalid", []):
        lines.append(f"DECISION INVALID (step {_d(d.get('step'))}): {_d(d.get('reason'), 160)} — nothing was proposed")
    proposals = by_type.get("action_proposed", [])
    for p in proposals:
        lines.append(f"PROPOSED: tool {_d(p.get('tool'))} · claimed grant {_d(p.get('claimed_grant_id', '—'))} · action digest {_d(p.get('action_digest', '—'), 16)}"
                     " — a proposal is not an execution")
    for d in by_type.get("preaction_declared", []):
        decl = d.get("declaration") if isinstance(d.get("declaration"), dict) else {}
        lines.append("DECLARED BEFORE ACTING: " + (" · ".join(f"{_d(k, 32)} {_d(v, 120)}" for k, v in sorted(decl.items(), key=lambda kv: str(kv[0]))) or "(empty declaration)"))
    claimed = {p.get("claimed_grant_id") for p in proposals if p.get("claimed_grant_id")}
    for gid in sorted(claimed, key=str):
        grant = next((g for g in view.grants() if g.get("grant_id") == gid), None)
        if grant is None:
            lines.append(f"AUTHORITY: claimed grant {_d(gid)} is NOT in this run's projection")
        else:
            lines.append(f"AUTHORITY: grant {_d(gid)} · tool {_d(grant.get('tool'))} · resources {_d(grant.get('resource_ids', []), 120)}"
                         f" · {'APPROVAL REQUIRED' if grant.get('requires_approval') else 'allowed without approval'}"
                         f"{' · REVOKED' if grant.get('revoked') else ''} · policy {_d(grant.get('policy_version', '—'))}"
                         f" · “{_d(grant.get('public_description', ''), 120)}”")
    gates = by_type.get("gate_decided", [])
    for g in gates:
        outcome = str(g.get("outcome", "?"))
        word = {"allow": "ALLOWED", "deny": "DENIED", "needs_approval": "NEEDS APPROVAL"}.get(outcome, outcome.upper())
        lines.append(f"GATE: {word} · reason {_d(g.get('reason'))} · resolved grant {_d(g.get('resolved_grant_id', '—'))}"
                     + (f" · after review {_d(g.get('resolution_of'))}" if g.get("resolution_of") else "")
                     + (" — an allow is not an execution" if outcome == "allow" else ""))
    if proposals and not gates:
        lines.append("GATE: no decision recorded for this proposal")
    effects = by_type.get("effect_observed", [])
    for e in effects:
        status = str(e.get("status", "?"))
        lines.append(f"EFFECT: {status.upper()} · receipt {_d(e.get('receipt_id', '—'), 16)}" + (f" · {_d(e.get('error'))}" if e.get("error") else ""))
        lines.extend(_rev_lines(e.get("before"), e.get("after")))
    if proposals and not effects:
        lines.append("EFFECT: NO EFFECT RECORDED — nothing changed by this proposal (a proposal or an allow is not an executed effect; "
                     "reads and refused effects record none)")
    for r in by_type.get("review_opened", []):
        lines.append(f"REVIEW: opened {_d(r.get('review_id'))} · recipient {_d(r.get('recipient_role', '—'))} · deadline {_d(r.get('deadline_at', '—'))}")
    for r in by_type.get("review_resolved", []):
        lines.append(f"REVIEW: resolved {_d(r.get('review_id'))} → {_d(r.get('status'))} · executed {_d(r.get('executed', '—'))}"
                     + (f" · {_d(r.get('note'), 120)}" if r.get("note") else ""))
    return "\n".join(lines)


@dataclass
class CockpitState:
    runs: list[dict[str, Any]] = field(default_factory=list)
    runs_refreshed_at: float | None = None
    health: dict[str, Any] | None = None
    health_refreshed_at: float | None = None
    reviews: dict[str, Any] | None = None
    selected: RunView | None = None
    generation: int = 0
    alerts: list[Alert] = field(default_factory=list)
    log: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    failures: int = 0  # consecutive read failures → backoff index

    # -- selection ----------------------------------------------------------------------------------
    def select(self, run_id: str | None) -> int:
        """Change the selected run; every in-flight response for the old selection is now stale."""
        self.generation += 1
        self.selected = RunView(run_id) if run_id else None
        return self.generation

    def current(self, generation: int) -> bool:
        return generation == self.generation

    # -- reads ----------------------------------------------------------------------------------------
    def apply_runs(self, body: dict[str, Any], now: float) -> None:
        self.runs = list(body.get("runs", []))
        self.runs_refreshed_at = now
        self.failures = 0

    def apply_health(self, body: dict[str, Any], now: float) -> None:
        self.health, self.health_refreshed_at = body, now

    def apply_snapshot(self, generation: int, body: dict[str, Any], now: float) -> bool:
        if not self.current(generation) or self.selected is None:
            return False
        self.selected = replace(self.selected, snapshot=body, refreshed_at=now)
        self.failures = 0
        return True

    def force_resync(self, reason: str) -> None:
        """Drop the selected run's cached events; the next refresh refetches from the genesis."""
        if self.selected is None:
            return
        view = self.selected
        self.selected = replace(view, events=(), next_cursor=0, resyncs=view.resyncs + 1)
        self.log.append(f"resync {view.run_id}: {reason}")

    def apply_events(self, generation: int, page: EventPage, now: float) -> str:
        """Append a page only if it continues the cached head EXACTLY; otherwise RESYNC (2/3's #28502).

        Checked: the page starts where the cache ends; the snapshot did not shrink; every `seq` is contiguous
        (first = last known + 1; a page at cursor 0 starts at genesis with prev_hash None); EVERY prev_hash link
        inside the page and across the boundary; every event names this run when it names one; increasing seq.
        """
        if not self.current(generation) or self.selected is None:
            return "stale"
        view = self.selected
        known = list(view.events)

        def resync(reason: str) -> str:
            self.selected = replace(view, events=(), next_cursor=0, resyncs=view.resyncs + 1, refreshed_at=now)
            self.log.append(f"resync {view.run_id}: {reason}")
            return "resync"

        if page.cursor != len(known):
            return resync(f"page cursor {page.cursor} != known {len(known)}")
        if page.total < len(known):
            return resync(f"snapshot shrank to {page.total} events (known {len(known)})")
        previous = known[-1] if known else None
        for index, event in enumerate(page.events):
            seq = event.get("seq")
            if not isinstance(seq, int) or isinstance(seq, bool):
                return resync(f"event without an integer seq at page index {index}")
            run_id = event.get("run_id")
            if run_id is not None and run_id != view.run_id:
                return resync(f"event {seq} names another run")
            if previous is None:
                # The initial prefix must be the ACTUAL genesis (2/3's #28526): cursor 0, seq 0, run_created, no prev_hash.
                if page.cursor != 0 or seq != 0 or event.get("event_type") != "run_created" or event.get("prev_hash") is not None:
                    return resync(f"first event is not the genesis (cursor {page.cursor}, seq {seq}, type {event.get('event_type')})")
            else:
                if seq != previous.get("seq", -1) + 1:
                    return resync(f"seq {seq} does not follow {previous.get('seq')}")
                if event.get("prev_hash") != previous.get("event_hash"):
                    return resync(f"chain discontinuity at seq {seq}")
            previous = event
        self.selected = replace(view, events=tuple(known + list(page.events)), next_cursor=page.next_cursor, refreshed_at=now)
        self.failures = 0
        return "appended" if page.events else "unchanged"

    def apply_verification(self, generation: int, body: dict[str, Any], now: float) -> str:
        """Bind the badge to the head identity the VERIFIER reported (`verified_head`: run_id, event_count, head_hash,
        from the seam), never to a hash borrowed from the view. Returns what was concluded:
        `bound` (identity for this run), `mismatch` (bound, but the view holds a different hash at the same count —
        the view is not the store's chain and is resynced), `wrong_run` (identity names another run → unbound),
        `unbound` (no usable identity), `stale` (an earlier selection's response; discarded)."""
        if not self.current(generation) or self.selected is None:
            return "stale"
        raw = body.get("verification")
        result: dict[str, Any] = raw if isinstance(raw, dict) else body
        view = self.selected
        head = body.get("verified_head")
        checked = result.get("checked_events")
        count = checked if isinstance(checked, int) and not isinstance(checked, bool) else -1
        identity, bound = "unbound", Head(count, None)
        if isinstance(head, dict):
            h_run, h_count, h_hash = head.get("run_id"), head.get("event_count"), head.get("head_hash")
            if h_run != view.run_id:
                identity = "wrong_run"
            elif isinstance(h_count, int) and not isinstance(h_count, bool) and isinstance(h_hash, str) and h_hash:
                bound = Head(h_count, h_hash)
                identity = "mismatch" if (h_count == view.head.count and h_hash != view.head.hash) else "bound"
        badge = VerificationBadge(head=bound, summary=str(result.get("summary", "?")),
                                  chain_consistent=bool(result.get("chain_consistent", False)),
                                  anchor=str(body.get("anchor_provenance", result.get("anchor_provenance", "?"))), at=now,
                                  identity=identity)
        self.selected = replace(view, verification=badge)
        if identity == "mismatch":
            self.force_resync(f"verifier head hash differs from the view's at seq {bound.count - 1}")
        return identity

    def read_failed(self) -> float:
        """Bounded exponential backoff for READS; reset by any success."""
        self.failures += 1
        return BACKOFF_S[min(self.failures, len(BACKOFF_S)) - 1]

    # -- freshness ----------------------------------------------------------------------------------
    @staticmethod
    def freshness(refreshed_at: float | None, now: float) -> str:
        if refreshed_at is None:
            return "OFFLINE"
        age = now - refreshed_at
        if age <= 1.0:
            return "LIVE"
        if age <= STALE_AFTER_S:
            return "FRESH"
        return "STALE"

    def may_mutate(self, now: float) -> bool:
        """Controls are offered only against a fresh projection of the selected run."""
        return (self.selected is not None and self.selected.refreshed_at is not None
                and now - self.selected.refreshed_at <= MUTATION_FRESHNESS_S)

    # -- derived alerts -----------------------------------------------------------------------------
    def derive_alerts(self, now: float) -> list[Alert]:
        alerts: list[Alert] = []
        sel = self.selected
        if sel and sel.verification and not sel.verification.chain_consistent:
            alerts.append(Alert("critical", "verification FAILED on the selected run", sel.run_id))
        for row in (self.reviews or {}).get("reviews", []):
            if row.get("open"):
                alerts.append(Alert("action", f"review waiting: {row.get('conflict', '?')}", row.get("run_id")))
        if sel and sel.verification and sel.verification.head != sel.head:
            badge = sel.verification
            if badge.identity == "wrong_run":
                what = "verification answered for another run"
            elif not badge.bound:
                what = "verification is not bound to this head"
            elif badge.head.count == sel.head.count and sel.head.hash is not None:
                what = "verified head differs from the view at the same seq"
            else:
                what = "head moved since the last verification"
            alerts.append(Alert("warning", f"{what}; verify again", sel.run_id))
        if sel and self.freshness(sel.refreshed_at, now) == "STALE":
            alerts.append(Alert("warning", "selected run view is STALE; controls disabled until a fresh read", sel.run_id))
        if self.health and str(self.health.get("provider", {}).get("status", "")) not in ("", "ok"):
            alerts.append(Alert("warning", f"local provider: {self.health['provider'].get('status')} (no fallback)"))
        self.alerts = alerts
        return alerts

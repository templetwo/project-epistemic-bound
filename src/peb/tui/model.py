"""The cockpit's state, and the pure rules that keep it honest.

Rules (each has a test):
- `seq` orders events; a page that does not continue the cached (count, head hash) is a discontinuity → the run's
  events are dropped and refetched from cursor 0 (RESYNC), never stitched.
- A selection generation counter: a response that belongs to an earlier selection is discarded.
- Verification is an explicit act on a specific head. `VerificationBadge` carries the head it verified; when the
  head moves the badge is STALE (shown as "verified at seq N, head now M"), never inherited (2/3's #28438).
  A consistent chain with no external anchor is shown as exactly that, never as "verified".
- Freshness is measured from the last successful refresh of that surface; mutations are offered only when the
  target run's projection is fresh (≤ `MUTATION_FRESHNESS_S`).
- Recorded ≠ started: the store's row says `running` from genesis; a run with zero `model_request` events shows
  "recorded, not started".
- Alerts and the operations log are UI derivations; nothing here writes evidence.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Any

from .transport import EventPage

MUTATION_FRESHNESS_S = 2.0
STALE_AFTER_S = 5.0
ACTIVE_POLL_S, WAITING_POLL_S, IDLE_POLL_S = 0.75, 2.0, 5.0
BACKOFF_S = (0.75, 1.5, 3.0, 6.0, 8.0)
TERMINAL = {"completed", "failed", "cancelled", "canceled"}


@dataclass(frozen=True)
class Head:
    count: int
    hash: str | None

    @staticmethod
    def of(events: list[dict[str, Any]]) -> Head:
        return Head(len(events), events[-1].get("event_hash") if events else None)


@dataclass(frozen=True)
class VerificationBadge:
    head: Head              # what was verified
    summary: str            # the verifier's own words, e.g. "chain_consistent; external_anchor_absent"
    chain_consistent: bool
    anchor: str             # anchor provenance as reported
    at: float               # monotonic time of the verification

    def label(self, current: Head) -> str:
        base = self.summary
        if current != self.head:
            return f"{base} — VERIFIED AT seq {self.head.count}, head now seq {current.count}: STALE, verify again"
        return base


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
        """What the run is doing, kept apart from the stored status."""
        if self.snapshot is None:
            return "loading"
        if self.status in TERMINAL:
            return self.status.upper()
        if self.status == "waiting_review":
            return "WAITING FOR REVIEW"
        if self.status == "paused":
            return "PAUSED"
        if not self.started:
            return "RECORDED — NOT STARTED"
        last = self.events[-1].get("event_type") if self.events else None
        return "MODEL WAIT" if last == "model_request" else "RUNNING"

    @property
    def model_calls(self) -> int:
        return sum(1 for e in self.events if e.get("event_type") == "model_request")

    @property
    def usage(self) -> dict[str, int | None]:
        """Token totals from recorded model_response payloads; unknown stays unknown (None), never zero."""
        prompt = completion = reasoning = None
        for e in self.events:
            if e.get("event_type") != "model_response":
                continue
            p = e.get("payload") or {}
            for key, acc in (("prompt_tokens", "prompt"), ("completion_tokens", "completion"), ("reasoning_tokens", "reasoning")):
                value = p.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    if acc == "prompt":
                        prompt = (prompt or 0) + value
                    elif acc == "completion":
                        completion = (completion or 0) + value
                    else:
                        reasoning = (reasoning or 0) + value
        return {"prompt": prompt, "completion": completion, "reasoning": reasoning}

    def poll_interval(self) -> float:
        if self.status in TERMINAL:
            return IDLE_POLL_S
        if self.status in ("waiting_review", "paused"):
            return WAITING_POLL_S
        return ACTIVE_POLL_S


@dataclass(frozen=True)
class Alert:
    level: str  # critical | action | warning | info
    text: str
    run_id: str | None = None


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

    def apply_events(self, generation: int, page: EventPage, now: float) -> str:
        """Append a page if it continues the cached head; otherwise RESYNC. Returns what happened."""
        if not self.current(generation) or self.selected is None:
            return "stale"
        view = self.selected
        known = list(view.events)
        if page.cursor != len(known):
            self.selected = replace(view, events=(), next_cursor=0, resyncs=view.resyncs + 1, refreshed_at=now)
            self.log.append(f"resync {view.run_id}: page cursor {page.cursor} != known {len(known)}")
            return "resync"
        if page.events:
            first_prev = page.events[0].get("prev_hash")
            expected = known[-1].get("event_hash") if known else None
            if known and first_prev != expected:
                self.selected = replace(view, events=(), next_cursor=0, resyncs=view.resyncs + 1, refreshed_at=now)
                self.log.append(f"resync {view.run_id}: chain discontinuity at seq {page.events[0].get('seq')}")
                return "resync"
            seqs = [e.get("seq") for e in page.events]
            ordered = all(isinstance(s, int) for s in seqs) and all(a < b for a, b in pairwise(seqs))
            if not ordered:
                self.selected = replace(view, events=(), next_cursor=0, resyncs=view.resyncs + 1, refreshed_at=now)
                self.log.append(f"resync {view.run_id}: page not in seq order")
                return "resync"
        self.selected = replace(view, events=tuple(known + page.events), next_cursor=page.next_cursor, refreshed_at=now)
        self.failures = 0
        return "appended" if page.events else "unchanged"

    def apply_verification(self, generation: int, body: dict[str, Any], now: float) -> bool:
        if not self.current(generation) or self.selected is None:
            return False
        raw = body.get("verification")
        result: dict[str, Any] = raw if isinstance(raw, dict) else body
        badge = VerificationBadge(head=self.selected.head, summary=str(result.get("summary", "?")),
                                  chain_consistent=bool(result.get("chain_consistent", False)),
                                  anchor=str(body.get("anchor_provenance", result.get("anchor_provenance", "?"))), at=now)
        self.selected = replace(self.selected, verification=badge)
        return True

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
        if self.selected and self.selected.verification and not self.selected.verification.chain_consistent:
            alerts.append(Alert("critical", "verification FAILED on the selected run", self.selected.run_id))
        for row in (self.reviews or {}).get("reviews", []):
            if row.get("open"):
                alerts.append(Alert("action", f"review waiting: {row.get('conflict', '?')}", row.get("run_id")))
        if self.selected and self.selected.verification and self.selected.verification.head != self.selected.head:
            alerts.append(Alert("warning", "head moved since the last verification; verify again", self.selected.run_id))
        if self.selected and self.freshness(self.selected.refreshed_at, now) == "STALE":
            alerts.append(Alert("warning", "selected run view is STALE; controls disabled until a fresh read", self.selected.run_id))
        if self.health and str(self.health.get("provider", {}).get("status", "")) not in ("", "ok"):
            alerts.append(Alert("warning", f"local provider: {self.health['provider'].get('status')} (no fallback)"))
        self.alerts = alerts
        return alerts

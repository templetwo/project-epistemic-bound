"""The terminal cockpit: an operator lens over the recorder (ADR-019).

Everything on screen comes from the workroom seam through a `CockpitTransport`; every string passes the
sanitizer; the state model decides what is fresh, what is stale, what resynced and what verification means.
Viewing writes nothing. Controls in this slice: refresh, select, run a scripted control, verify, export,
pause/cancel/resume, review ack/allow/deny, step/begin. Every mutation refetches instead of retrying.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Label, RichLog, Static, TabbedContent, TabPane

from .model import CockpitState, format_usage, inspect_event
from .sanitize import display
from .transport import (
    OPERATOR_BEHAVIOUR,
    CockpitTransport,
    NotSignedIn,
    TransportError,
    UncertainOutcome,
)

HEALTH_EVERY_S, RUNS_EVERY_S, REVIEWS_EVERY_S = 15.0, 2.0, 3.0
EVENT_PAGE = 100


def _cells(*values: str) -> list[Text]:
    """DataTable cells as rich Text objects: literal, never interpreted as markup."""
    return [Text(v) for v in values]


def _short(value: Any, n: int = 12) -> str:
    text = display(value, one_line=True, max_chars=200)
    return text if len(text) <= n else text[:n] + "…"


class PromptScreen(ModalScreen[str | None]):
    """One line of operator input with the exact target shown; Escape cancels. Never used for the secret."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, hint: str, placeholder: str = "", must_equal: str | None = None) -> None:
        super().__init__()
        self._title, self._hint, self._placeholder, self._must_equal = title, hint, placeholder, must_equal

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt"):
            yield Label(Content(display(self._title, one_line=True)), id="prompt-title", markup=False)
            yield Label(Content(display(self._hint)), id="prompt-hint", markup=False)
            yield Input(placeholder=self._placeholder, id="prompt-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if self._must_equal is not None and value != self._must_equal:
            self.query_one("#prompt-hint", Label).update(Content("That did not match. Escape to cancel."))
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ReviewPickScreen(ModalScreen[dict | None]):
    """Choose the EXACT review to act on (outside reviewer, pass 2, item 1): every open review of the selected run is
    listed; ↑/↓ moves, Enter chooses, Escape cancels. Nothing is sent from here."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, run_id: str, decision: str, reviews: list[dict[str, Any]]) -> None:
        super().__init__()
        self._run_id, self._decision, self._reviews = run_id, decision, reviews

    def compose(self) -> ComposeResult:
        with Vertical(id="review-pick"):
            yield Label(Content(display(f"{self._decision.upper()} — choose the exact review on {self._run_id} "
                                        f"({len(self._reviews)} open): ↑/↓ then Enter · Escape cancels", one_line=True)),
                        id="review-pick-title", markup=False)
            yield DataTable(id="review-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#review-table", DataTable)
        table.add_columns("review", "status", "conflict", "proposal", "deadline")
        for r in self._reviews:
            table.add_row(*_cells(_short(r.get("review_id", ""), 20), display(r.get("status", ""), one_line=True),
                                  _short(r.get("conflict", ""), 24), _short(r.get("proposal_id", ""), 20),
                                  _short(str(r.get("deadline_at", ""))[11:19], 8)), key=str(r.get("review_id", "")))
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value) if event.row_key is not None else None
        self.dismiss(next((r for r in self._reviews if str(r.get("review_id")) == key), None))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ReviewConfirmScreen(ModalScreen[bool]):
    """The chosen review's recorded context before allow/deny/ack: its run and current state, the proposal, the
    pre-action declaration, the claimed grant's actual scope, the gate's decision so far, and what (if anything)
    changed. `y` sends exactly this decision for exactly this review; `n` / Escape cancels. The backend re-validates
    independently; the cockpit re-reads the target right before sending and refuses if it changed."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("y", "confirm", "Send"), Binding("n", "cancel", "Cancel"),
                                         Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, context: str) -> None:
        super().__init__()
        self._title, self._context_text = title, context

    def compose(self) -> ComposeResult:
        with Vertical(id="review-confirm"):
            yield Label(Content(display(self._title, one_line=True)), id="review-confirm-title", markup=False)
            yield Static(Content(display(self._context_text, max_chars=6000)), id="review-context", markup=False)
            yield Label(Content("y = send exactly this decision for exactly this review · n / Escape = cancel · one attempt, never retried"),
                        id="review-confirm-hint", markup=False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class CockpitApp(App[None]):
    """`peb tui`. One transport, one state, a polling worker, and keys that map onto closed operations."""

    TITLE = "PROJECT EPISTEMIC BOUND — cockpit"
    CSS = """
    #status { height: 1; background: $panel; padding: 0 1; }
    #alerts { height: 3; padding: 0 1; color: $warning; }
    #runs { width: 34; }
    #detail { width: 1fr; }
    #overview { height: auto; padding: 0 1; }
    #prompt { width: 80; height: auto; border: round $accent; padding: 1 2; background: $surface; }
    PromptScreen { align: center middle; }
    #review-pick { width: 100; height: auto; max-height: 20; border: round $accent; padding: 1 2; background: $surface; }
    #review-table { height: auto; max-height: 12; }
    ReviewPickScreen { align: center middle; }
    #review-confirm { width: 110; height: auto; max-height: 36; border: round $warning; padding: 1 2; background: $surface; }
    #review-context { height: auto; max-height: 28; overflow-y: auto; }
    ReviewConfirmScreen { align: center middle; }
    RichLog { height: 6; border-top: solid $panel; }
    """
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit (detaches; runs and a started workroom keep going)"),
        Binding("g", "refresh_now", "Refresh"),
        Binding("n", "demo", "Scripted control"),
        Binding("v", "verify", "Verify"),
        Binding("e", "export", "Export"),
        Binding("h", "pause", "Pause"),
        Binding("u", "resume", "Resume"),
        Binding("x", "cancel_run", "Cancel run"),
        Binding("s", "step", "Step"),
        Binding("b", "begin", "Begin"),
        Binding("a", "review_ack", "Ack review"),
        Binding("l", "review_allow", "Allow review"),
        Binding("d", "review_deny", "Deny review"),
        Binding("z", "toggle_clock", "UTC/local"),
    ]

    def __init__(self, transport: CockpitTransport, *, clock: Callable[[], float] = time.monotonic, poll: bool = True,
                 secret: str | None = None) -> None:
        super().__init__()
        self.transport = transport
        self._secret = secret  # consumed by the first sign-in inside the app's own event loop, then dropped
        self.state = CockpitState()
        self.clock = clock
        self._poll = poll
        self._rendered_events = 0
        self._inspect_index: int | None = None  # the event row the inspector shows; re-rendered as the chain grows
        self._last_health = self._last_runs = self._last_reviews = -1e9
        self._local_time = True
        self._stopping = False
        self.rendered: dict[str, str] = {}  # what each pane last showed (sanitized text); the tests read this
        self.last_inventory: list[dict[str, Any]] = []  # read fresh at quit; drives the child-workroom decision
        self.inventory_confirmed = False

    # -- layout -------------------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static("connecting…", id="status", markup=False)
        with Horizontal():
            yield DataTable(id="runs", cursor_type="row", zebra_stripes=True)
            with Vertical(id="detail"):
                yield Static("select a run", id="overview", markup=False)
                with TabbedContent(id="tabs"):
                    with TabPane("Events", id="tab-events"):
                        yield DataTable(id="events", cursor_type="row")
                    with TabPane("Inspect", id="tab-inspect"):
                        yield Static("select an event in the Events tab", id="inspect", markup=False)
                    with TabPane("Permissions", id="tab-permissions"):
                        yield Static("", id="permissions", markup=False)
                    with TabPane("Commitments", id="tab-commitments"):
                        yield Static("", id="commitments", markup=False)
                    with TabPane("Reviews", id="tab-reviews"):
                        yield Static("", id="reviews", markup=False)
                    with TabPane("Evidence", id="tab-evidence"):
                        yield Static("", id="evidence", markup=False)
        yield Static("", id="alerts", markup=False)
        yield RichLog(id="oplog", markup=False, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        runs = self.query_one("#runs", DataTable)
        runs.add_columns("run", "status", "mode", "created")
        events = self.query_one("#events", DataTable)
        events.add_columns("seq", "time", "event", "actor", "hash")
        if self._poll:
            self.poll_loop()

    # -- polling ------------------------------------------------------------------------------------
    @work(exclusive=True, group="poll")
    async def poll_loop(self) -> None:
        if self._secret is not None:
            try:
                await self.transport.sign_in(self._secret)
            except TransportError as e:
                self.log_line(f"sign-in failed ({e.code}): {display(e.message, one_line=True)}")
                self._stopping = True
                return
            finally:
                self._secret = None
        while not self._stopping:
            try:
                await self.refresh_all()
                delay = self.state.selected.poll_interval() if self.state.selected else RUNS_EVERY_S
            except TransportError as e:
                delay = self.state.read_failed()
                self.log_line(f"read failed ({e.code}): {display(e.message, one_line=True)}; retry in {delay:.2f}s")
                self.render_status()
            await asyncio.sleep(delay)

    async def refresh_all(self) -> None:
        now = self.clock()
        if now - self._last_health >= HEALTH_EVERY_S:
            self.state.apply_health(await self.transport.health(), self.clock())
            self._last_health = now
        if now - self._last_runs >= RUNS_EVERY_S or self.state.selected is None:
            self.state.apply_runs(await self.transport.list_runs(), self.clock())
            self._last_runs = now
            self.render_runs()
        if now - self._last_reviews >= REVIEWS_EVERY_S:
            self.state.reviews = await self.transport.reviews()
            self._last_reviews = now
        if self.state.selected is not None:
            await self.refresh_selected()
        self.state.derive_alerts(self.clock())
        self.render_status()
        self.render_alerts()

    async def refresh_selected(self) -> None:
        """Events first (pages until the end of the current snapshot), then the projection, all under one generation."""
        view = self.state.selected
        if view is None:
            return
        generation = self.state.generation
        cursor = 0 if view.next_cursor is None else view.next_cursor
        if view.next_cursor is None:
            cursor = len(view.events)  # ask again from our head: an empty page means nothing new
        for _ in range(50):  # bounded: a run has bounded events
            page = await self.transport.events(view.run_id, cursor=cursor, limit=EVENT_PAGE)
            outcome = self.state.apply_events(generation, page, self.clock())
            if outcome in ("stale", "resync"):
                if outcome == "resync":
                    self._rendered_events = 0
                    self.query_one("#events", DataTable).clear()
                    self.log_line(f"resync {view.run_id}: evidence refetched from the start")
                break
            cursor = len(self.state.selected.events) if self.state.selected else 0
            if page.next_cursor is None or not page.events:
                break
        snapshot = await self.transport.get_run(view.run_id)
        if self.state.apply_snapshot(generation, snapshot, self.clock()):
            self.render_selected()

    # -- rendering ----------------------------------------------------------------------------------
    def _set(self, widget_id: str, text: str) -> None:
        """Every pane is LITERAL: a Content object (never markup), on a widget created with markup=False (2/3's #28502)."""
        self.rendered[widget_id] = text
        self.query_one(f"#{widget_id}", Static).update(Content(text))

    def render_status(self) -> None:
        now = self.clock()
        health = self.state.health or {}
        provider = (health.get("provider") or {}).get("status", "?")
        storage = (health.get("storage") or {}).get("status", "?")
        sel = self.state.selected
        fresh = self.state.freshness(sel.refreshed_at if sel else None, now) if sel else self.state.freshness(self.state.runs_refreshed_at, now)
        stamp = time.strftime("%H:%M:%S", time.localtime() if self._local_time else time.gmtime()) + (" local" if self._local_time else " UTC")
        text = (f"HEALTH storage {display(storage, one_line=True)} · local provider {display(provider, one_line=True)} · "
                f"runs {len(self.state.runs)} · view {fresh} · {stamp} · {display(self.transport.base_url, one_line=True)}")
        self._set("status", text)

    def render_runs(self) -> None:
        table = self.query_one("#runs", DataTable)
        keep = self.state.selected.run_id if self.state.selected else None
        table.clear()
        for run in reversed(self.state.runs):
            rid = str(run.get("run_id", ""))
            table.add_row(*_cells(_short(rid, 16), display(run.get("status", ""), one_line=True), _short(run.get("mode", ""), 18),
                                  _short(str(run.get("created_at", ""))[11:19], 8)), key=rid)
        if keep and any(str(r.get("run_id")) == keep for r in self.state.runs):
            index = [str(r.get("run_id")) for r in reversed(self.state.runs)].index(keep)
            table.move_cursor(row=index)

    def render_selected(self) -> None:
        view = self.state.selected
        if view is None or view.snapshot is None:
            return
        run = view.snapshot.get("run") or {}
        manifest = run.get("manifest") or {}
        settings = manifest.get("settings") or {}
        overview = "\n".join([
            f"run {display(view.run_id, one_line=True)}   status {display(view.status, one_line=True)}   activity {view.activity}",
            (f"provider {display(manifest.get('provider_kind'), one_line=True)} · model requested {display(manifest.get('model_requested'), one_line=True)}"
             f" · resolved {display(manifest.get('model_resolved') or '—', one_line=True)} · artifact digest — not recorded"),
            (f"profile {display(manifest.get('profile_id'), one_line=True)} ({display(settings.get('arm', '?'), one_line=True)})"
             f" · task {display(manifest.get('task_id'), one_line=True)} · frame {display(settings.get('frame', '?'), one_line=True)}"),
            f"calls {view.model_calls} / {display((manifest.get('limits') or {}).get('max_model_calls', '?'), one_line=True)}",
            format_usage(view.usage),
        ])
        self._set("overview", overview)
        # events: append only what is new since the last render (resync clears)
        table = self.query_one("#events", DataTable)
        for event in view.events[self._rendered_events:]:
            ts = str(event.get("ts", ""))
            table.add_row(*_cells(str(event.get("seq", "")), display(ts[11:19], one_line=True), display(event.get("event_type", ""), one_line=True),
                                  display(event.get("actor", ""), one_line=True), _short(event.get("event_hash", ""), 10)))
        self._rendered_events = len(view.events)
        if self._inspect_index is not None:
            self._set("inspect", inspect_event(view, self._inspect_index))
        grants = run.get("grants") or []
        self._set("permissions", "\n".join(
            f"{display(g.get('tool'), one_line=True):18} {'APPROVAL' if g.get('requires_approval') else 'ALLOWED':8} "
            f"{'REVOKED ' if g.get('revoked') else ''}policy {display(g.get('policy_version'), one_line=True)} · {display(g.get('public_description', ''), one_line=True, max_chars=80)}"
            for g in grants) or "no grants in the projection (permissions are the reference monitor's; commitments are not permissions)")
        commitments = run.get("commitments") or []
        self._set("commitments", "\n".join(
            f"{display(c.get('commitment_id'), one_line=True)} {display(c.get('kind'), one_line=True)} {display(c.get('status'), one_line=True)}"
            f" origin {display(c.get('origin'), one_line=True)}: {display(c.get('text', ''), one_line=True, max_chars=100)}"
            for c in commitments) or "no commitments recorded (a commitment grants no permission)")
        reviews = view.snapshot.get("reviews") or []
        held = view.snapshot.get("held") or {}
        self._set("reviews", "\n".join(
            f"{display(r.get('review_id'), one_line=True)} {display(r.get('status'), one_line=True)} · {display(r.get('conflict'), one_line=True)}"
            f" · deadline {display(r.get('deadline_at'), one_line=True)}{' · HELD proposal' if r.get('review_id') in held else ''}"
            for r in reviews) or "no review requests in this run (acknowledgement grants no authority)")
        head = view.head
        badge = view.verification.label(head) if view.verification else "not verified in this session — press V (explicit; never inferred from freshness)"
        anchor = view.verification.anchor if view.verification else "—"
        self._set("evidence", "\n".join([
            f"HEAD seq {head.count - 1 if head.count else '—'} · events {head.count} · head hash {display(head.hash or '—', one_line=True)}",
            f"VERIFICATION {badge}",
            f"ANCHOR {display(anchor, one_line=True)}   (a consistent chain with no external anchor is not 'verified')",
            f"resyncs this session {view.resyncs}",
        ]))

    def render_alerts(self) -> None:
        lines = [f"[{a.level.upper()}] {display(a.text, one_line=True)}" for a in self.state.alerts[:3]]
        self._set("alerts", "\n".join(lines))

    def log_line(self, text: str) -> None:
        self.state.log.append(text)
        self.query_one("#oplog", RichLog).write(display(text, one_line=True, max_chars=300))

    # -- selection ----------------------------------------------------------------------------------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "events":
            view = self.state.selected
            if view is not None and event.cursor_row is not None:
                self._inspect_index = int(event.cursor_row)
                self._set("inspect", inspect_event(view, self._inspect_index))
            return
        if event.data_table.id != "runs" or event.row_key is None:
            return
        run_id = str(event.row_key.value)
        if self.state.selected and self.state.selected.run_id == run_id:
            return
        self.state.select(run_id)
        self._rendered_events = 0
        self._inspect_index = None
        self._set("inspect", "select an event in the Events tab")
        self.query_one("#events", DataTable).clear()
        self._set("overview", f"loading {display(run_id, one_line=True)}…")
        self.run_worker(self._refresh_selected_now(), exclusive=True, group="select")

    async def _refresh_selected_now(self) -> None:
        try:
            await self.refresh_selected()
            self.state.derive_alerts(self.clock())
            self.render_status()
            self.render_alerts()
        except TransportError as e:
            self.log_line(f"read failed ({e.code}): {display(e.message, one_line=True)}")

    # -- actions (every mutation: one attempt, then refetch) ----------------------------------------
    async def _mutate(self, label: str, call: Callable[[], Any]) -> Any:
        if not self.state.may_mutate(self.clock()) and label not in ("demo",):
            self.log_line(f"{label}: refused locally — the selected run's view is not fresh; refreshing first")
            await self._refresh_selected_now()
            if not self.state.may_mutate(self.clock()):
                return None
        try:
            result = await call()
            self.log_line(f"{label}: recorded")
        except UncertainOutcome as e:
            self.log_line(f"{label}: RESULT UNKNOWN — {OPERATOR_BEHAVIOUR['uncertain'][0]}")
            result = None
            _ = e
        except NotSignedIn:
            self.log_line(f"{label}: session expired; sign in again (restart the cockpit)")
            return None
        except TransportError as e:
            hint = OPERATOR_BEHAVIOUR.get(e.code, ("", False))[0]
            self.log_line(f"{label}: refused ({e.code}) {display(e.message, one_line=True)} — {hint}")
            result = None
        self._last_runs = -1e9
        await self._safe_refresh_all()
        return result

    async def _safe_refresh_all(self) -> None:
        try:
            await self.refresh_all()
        except TransportError as e:
            self.log_line(f"read failed ({e.code}): {display(e.message, one_line=True)}")

    def _selected_id(self) -> str | None:
        return self.state.selected.run_id if self.state.selected else None

    async def action_refresh_now(self) -> None:
        self._last_health = self._last_runs = self._last_reviews = -1e9
        await self._safe_refresh_all()

    def action_toggle_clock(self) -> None:
        self._local_time = not self._local_time
        self.render_status()

    async def action_demo(self) -> None:
        def after(value: str | None) -> None:
            if not value:
                return
            parts = value.split()
            case, frame = parts[0], (parts[1] if len(parts) > 1 else "ordinary")
            self.run_worker(self._mutate("demo", lambda: self.transport.demo(case, frame)), exclusive=True, group="mutate")

        self.push_screen(PromptScreen("Run a scripted control (no model, no network, a fresh run)",
                                      "case [frame]: truthful-repair | authorized-concealment | forbidden-export; frame ordinary|game|roleplay|evaluation",
                                      "truthful-repair ordinary"), after)

    async def action_verify(self) -> None:
        rid = self._selected_id()
        if rid is None:
            return
        generation = self.state.generation
        try:
            body = await self.transport.verify(rid)
        except TransportError as e:
            self.log_line(f"verify: refused ({e.code}) {display(e.message, one_line=True)}")
            return
        identity = self.state.apply_verification(generation, body, self.clock())
        if identity == "stale":
            return
        summary = display((body.get('verification') or {}).get('summary', '?'), one_line=True)
        note = {"bound": "bound to the verifier's head", "unbound": "UNBOUND — the verifier reported no head identity",
                "wrong_run": "UNBOUND — the verifier answered for another run",
                "mismatch": "the verifier's head hash differs from the view's at the same seq — view resynced"}[identity]
        self.log_line(f"verify {rid}: {summary} · {note}")
        if identity == "mismatch":
            self._rendered_events = 0
            self.query_one("#events", DataTable).clear()
            await self._refresh_selected_now()
        self.state.derive_alerts(self.clock())
        self.render_selected()
        self.render_alerts()

    async def action_export(self) -> None:
        rid = self._selected_id()
        if rid is None:
            return

        def after(value: str | None) -> None:
            if value:
                self.run_worker(self._mutate("export", lambda: self.transport.export(rid, value)), exclusive=True, group="mutate")

        self.push_screen(PromptScreen(f"Export evidence bundle for {rid}", "absolute output directory on this computer; no upload", "/absolute/path"), after)

    async def action_pause(self) -> None:
        rid = self._selected_id()
        if rid:
            await self._mutate("pause", lambda: self.transport.pause_run(rid))

    async def action_resume(self) -> None:
        rid = self._selected_id()
        if rid:
            await self._mutate("resume", lambda: self.transport.resume_run(rid))

    async def action_step(self) -> None:
        rid = self._selected_id()
        if rid:
            await self._mutate("step", lambda: self.transport.step_run(rid))

    async def action_begin(self) -> None:
        rid = self._selected_id()
        if rid:
            await self._mutate("begin", lambda: self.transport.begin_run(rid))

    async def action_cancel_run(self) -> None:
        rid = self._selected_id()
        view = self.state.selected
        if rid is None or view is None:
            return
        head = view.head

        def after(value: str | None) -> None:
            if value == rid[-6:]:
                self.run_worker(self._mutate("cancel", lambda: self.transport.cancel_run(rid)), exclusive=True, group="mutate")

        self.push_screen(PromptScreen(f"CANCEL RUN {rid}",
                                      f"head seq {head.count - 1 if head.count else '—'} · status {view.status}. This terminates the run; it does not delete evidence. "
                                      f"Type the final 6 run-id characters to confirm.", rid[-6:], must_equal=rid[-6:]), after)

    # -- reviews: choose the exact review, see its recorded context, confirm, re-read, send once -----
    def _review_context(self, view: Any, review: dict[str, Any]) -> str:
        """What the record holds for this review: the run and its current state, the review itself, and the linked
        decision story (proposal, declaration, claimed grant's scope, gate so far, effect so far) from the cached chain."""
        rid = view.run_id
        held = (view.snapshot or {}).get("held") or {}
        review_id = str(review.get("review_id"))
        lines = [
            f"RUN {rid} · stored status {display(view.status, one_line=True)} · activity {view.activity} · head seq {view.head.count - 1 if view.head.count else '—'}",
            (f"REVIEW {review_id} · status {display(review.get('status'), one_line=True)} · conflict {display(review.get('conflict', '—'), one_line=True)}"
             f" · deadline {display(review.get('deadline_at', '—'), one_line=True)}{' · HELD proposal' if review_id in held else ''}"),
        ]
        proposal_id = review.get("proposal_id") or held.get(review_id)
        index = None
        if proposal_id is not None:
            for i, ev in enumerate(view.events):
                p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
                if ev.get("event_type") == "action_proposed" and p.get("proposal_id") == proposal_id:
                    index = i
                    break
        lines.append(inspect_event(view, index) if index is not None else
                     "no proposal event for this review is in the cached chain (refresh, or the review was opened without a proposal)")
        lines.append("Acknowledgement grants no authority. Allow re-gates the HELD proposal against current grants and state; deny records the refusal. "
                     "The backend validates independently of this screen.")
        return "\n".join(lines)

    async def _send_review(self, rid: str, review_id: str, decision: str, shown_review_status: str, shown_run_status: str) -> None:
        """Re-read the target RIGHT BEFORE sending; if the review's status or the run's status differs from what the
        operator was SHOWN when confirming, nothing is sent and the change is named — the cockpit never silently
        switches targets."""
        try:
            fresh = await self.transport.get_run(rid)
        except TransportError as e:
            self.log_line(f"review {decision} {review_id}: could not re-read the run ({e.code}); nothing sent")
            return
        generation = self.state.generation
        if self.state.selected and self.state.selected.run_id == rid:
            self.state.apply_snapshot(generation, fresh, self.clock())
        current = next((r for r in (fresh.get("reviews") or []) if str(r.get("review_id")) == review_id), None)
        run_status = str(fresh.get("status", "unknown"))
        if current is None or str(current.get("status")) != shown_review_status or run_status != shown_run_status:
            was, now = display(shown_review_status, one_line=True), display(current.get("status") if current else "absent", one_line=True)
            self.log_line(f"review {decision} {review_id}: target changed since confirmation (review {was} → {now}; run {shown_run_status} → {run_status}); nothing sent")
            self.render_selected()
            return
        await self._mutate(f"review {decision} {review_id}", lambda: self.transport.resolve_review(rid, review_id, decision))

    async def _review(self, decision: str) -> None:
        rid = self._selected_id()
        view = self.state.selected
        if rid is None or view is None or view.snapshot is None:
            return
        open_reviews = view.open_reviews()
        if not open_reviews:
            self.log_line(f"review {decision}: no open review on {rid}")
            return
        shown_run_status = view.status

        def chosen(review: dict[str, Any] | None) -> None:
            if review is None:
                self.log_line(f"review {decision}: cancelled at selection; nothing sent")
                return
            review_id = str(review.get("review_id"))
            shown_review_status = str(review.get("status"))  # what the operator is shown, captured as a value
            context = self._review_context(view, review)

            def confirmed(ok: bool) -> None:
                if not ok:
                    self.log_line(f"review {decision} {review_id}: cancelled; nothing sent")
                    return
                self.run_worker(self._send_review(rid, review_id, decision, shown_review_status, shown_run_status), exclusive=True, group="mutate")

            self.push_screen(ReviewConfirmScreen(f"{decision.upper()} review {review_id} on {rid}?", context), confirmed)

        self.push_screen(ReviewPickScreen(rid, decision, open_reviews), chosen)

    async def action_review_ack(self) -> None:
        await self._review("ack")

    async def action_review_allow(self) -> None:
        await self._review("allow")

    async def action_review_deny(self) -> None:
        await self._review("deny")

    async def action_quit(self) -> None:
        """Leave the cockpit. A FRESH inventory is read right now and handed to the caller as INFORMATION for its quit
        notice (2/3's #28511: no read is a shutdown interlock; a started workroom is always left running)."""
        self._stopping = True
        try:
            fresh = await self.transport.list_runs()
            self.last_inventory = list(fresh.get("runs", []))
            self.inventory_confirmed = True
        except TransportError as e:
            self.last_inventory = list(self.state.runs)
            self.inventory_confirmed = False
            self.log_line(f"quit: could not read the inventory ({e.code}); the notice will say so")
        try:
            await self.transport.close()
        finally:
            self.exit()

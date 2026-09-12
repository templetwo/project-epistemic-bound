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

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Label, RichLog, Static, TabbedContent, TabPane

from .model import CockpitState
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
            yield Label(display(self._title, one_line=True), id="prompt-title")
            yield Label(display(self._hint), id="prompt-hint")
            yield Input(placeholder=self._placeholder, id="prompt-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if self._must_equal is not None and value != self._must_equal:
            self.query_one("#prompt-hint", Label).update("That did not match. Escape to cancel.")
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


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
    RichLog { height: 6; border-top: solid $panel; }
    """
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit (the run keeps going)"),
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
        self._last_health = self._last_runs = self._last_reviews = -1e9
        self._local_time = True
        self._stopping = False
        self.rendered: dict[str, str] = {}  # what each pane last showed (sanitized text); the tests read this

    # -- layout -------------------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static("connecting…", id="status")
        with Horizontal():
            yield DataTable(id="runs", cursor_type="row", zebra_stripes=True)
            with Vertical(id="detail"):
                yield Static("select a run", id="overview")
                with TabbedContent(id="tabs"):
                    with TabPane("Events", id="tab-events"):
                        yield DataTable(id="events", cursor_type="row")
                    with TabPane("Permissions", id="tab-permissions"):
                        yield Static("", id="permissions")
                    with TabPane("Commitments", id="tab-commitments"):
                        yield Static("", id="commitments")
                    with TabPane("Reviews", id="tab-reviews"):
                        yield Static("", id="reviews")
                    with TabPane("Evidence", id="tab-evidence"):
                        yield Static("", id="evidence")
        yield Static("", id="alerts")
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
        self.rendered[widget_id] = text
        self.query_one(f"#{widget_id}", Static).update(text)

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
            table.add_row(_short(rid, 16), display(run.get("status", ""), one_line=True), _short(run.get("mode", ""), 18),
                          _short(str(run.get("created_at", ""))[11:19], 8), key=rid)
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
        usage = view.usage
        fmt = lambda v: "—" if v is None else str(v)
        overview = "\n".join([
            f"run {display(view.run_id, one_line=True)}   status {display(view.status, one_line=True)}   activity {view.activity}",
            (f"provider {display(manifest.get('provider_kind'), one_line=True)} · model requested {display(manifest.get('model_requested'), one_line=True)}"
             f" · resolved {display(manifest.get('model_resolved') or '—', one_line=True)} · artifact digest — not recorded"),
            (f"profile {display(manifest.get('profile_id'), one_line=True)} ({display(settings.get('arm', '?'), one_line=True)})"
             f" · task {display(manifest.get('task_id'), one_line=True)} · frame {display(settings.get('frame', '?'), one_line=True)}"),
            (f"calls {view.model_calls} / {display((manifest.get('limits') or {}).get('max_model_calls', '?'), one_line=True)}"
             f" · tokens in {fmt(usage['prompt'])} / out {fmt(usage['completion'])} / reasoning {fmt(usage['reasoning'])}"),
        ])
        self._set("overview", overview)
        # events: append only what is new since the last render (resync clears)
        table = self.query_one("#events", DataTable)
        for event in view.events[self._rendered_events:]:
            ts = str(event.get("ts", ""))
            table.add_row(str(event.get("seq", "")), display(ts[11:19], one_line=True), display(event.get("event_type", ""), one_line=True),
                          display(event.get("actor", ""), one_line=True), _short(event.get("event_hash", ""), 10))
        self._rendered_events = len(view.events)
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
        if event.data_table.id != "runs" or event.row_key is None:
            return
        run_id = str(event.row_key.value)
        if self.state.selected and self.state.selected.run_id == run_id:
            return
        self.state.select(run_id)
        self._rendered_events = 0
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
        if self.state.apply_verification(generation, body, self.clock()):
            self.log_line(f"verify {rid}: {display((body.get('verification') or {}).get('summary', '?'), one_line=True)}")
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

    async def _review(self, decision: str) -> None:
        rid = self._selected_id()
        view = self.state.selected
        if rid is None or view is None or view.snapshot is None:
            return
        open_reviews = [r for r in (view.snapshot.get("reviews") or []) if r.get("status") in ("pending", "acknowledged")]
        if not open_reviews:
            self.log_line(f"review {decision}: no open review on {rid}")
            return
        review = open_reviews[0]
        await self._mutate(f"review {decision}", lambda: self.transport.resolve_review(rid, str(review.get("review_id")), decision))

    async def action_review_ack(self) -> None:
        await self._review("ack")

    async def action_review_allow(self) -> None:
        await self._review("allow")

    async def action_review_deny(self) -> None:
        await self._review("deny")

    async def action_quit(self) -> None:
        self._stopping = True
        try:
            await self.transport.close()
        finally:
            self.exit()

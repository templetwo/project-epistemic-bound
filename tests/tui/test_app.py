"""The cockpit, headless: viewing writes nothing; selection, refresh and the honesty rules reach the screen; every
control maps to exactly one closed operation and refetches afterwards; hostile strings render inert."""
from __future__ import annotations

import asyncio

import pytest
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Static

from peb.tui.app import CockpitApp
from peb.tui.transport import TransportError
from tests.tui.fake_transport import FakeTransport, event


def _app(t: FakeTransport, poll: bool = False) -> CockpitApp:
    ticks = [100.0]

    def clock() -> float:
        ticks[0] += 0.1
        return ticks[0]

    return CockpitApp(t, clock=clock, poll=poll)


def test_viewing_writes_nothing_and_shows_recorded_not_started():
    async def scenario():
        t = FakeTransport()
        t.add_run("run_" + "a" * 32, "running")
        app = _app(t)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.refresh_all()
            await pilot.pause()
            assert t.mutations() == []
            runs = app.query_one("#runs", DataTable)
            assert runs.row_count == 1
            # highlighting the row selects it; the projection and the events arrive
            runs.move_cursor(row=0)
            await pilot.pause()
            await app.refresh_all()
            await pilot.pause()
            assert app.state.selected and app.state.selected.run_id == "run_" + "a" * 32
            overview = app.rendered["overview"]
            assert "RECORDED — NOT STARTED" in overview and "artifact digest — not recorded" in overview and "tokens in —" in overview
            evidence = app.rendered["evidence"]
            assert "not verified in this session" in evidence and "external anchor is not 'verified'" in evidence
            assert t.mutations() == []  # selection + refresh: reads only

    asyncio.run(scenario())


def test_verify_pins_the_badge_and_a_new_head_marks_it_stale():
    async def scenario():
        t = FakeTransport()
        rid = "run_" + "b" * 32
        t.add_run(rid, "running", events=[event(0, "run_created", None, "supervisor"), event(1, "model_request", "h0")])
        app = _app(t)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.refresh_all(); await pilot.pause()
            app.query_one("#runs", DataTable).move_cursor(row=0); await pilot.pause()
            await app.refresh_all(); await pilot.pause()
            await pilot.press("v"); await pilot.pause()
            assert t.mutations() == ["verify"]
            evidence = app.rendered["evidence"]
            assert "chain_consistent; external_anchor_absent" in evidence and "STALE" not in evidence
            # the run records a new event; the next refresh appends it and the badge is stale, never inherited
            t.events_by_run[rid].append(event(2, "model_response", "h1", payload={"prompt_tokens": 3, "completion_tokens": None}))
            await app.refresh_all(); await pilot.pause()
            evidence = app.rendered["evidence"]
            assert "STALE" in evidence and "seq 1" in evidence and "seq 2" in evidence
            assert app.query_one("#events", DataTable).row_count == 3
            assert "tokens in 3 / out —" in app.rendered["overview"]

    asyncio.run(scenario())


def test_a_chain_gap_resyncs_instead_of_stitching():
    async def scenario():
        t = FakeTransport()
        rid = "run_" + "c" * 32
        t.add_run(rid, "running", events=[event(0, "run_created", None, "supervisor"), event(1, "model_request", "h0")])
        app = _app(t)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.refresh_all(); await pilot.pause()
            app.query_one("#runs", DataTable).move_cursor(row=0); await pilot.pause()
            await app.refresh_all(); await pilot.pause()
            assert app.query_one("#events", DataTable).row_count == 2
            # the store's history is rewritten under us (a different chain): the cockpit must not stitch
            t.events_by_run[rid] = [event(0, "run_created", None, "supervisor"), {**event(1, "model_request", "h0"), "event_hash": "zz1"},
                                    event(2, "model_response", "zz1")]
            await app.refresh_all(); await pilot.pause()
            assert app.state.selected.resyncs >= 1
            await app.refresh_all(); await pilot.pause()
            assert [e["event_hash"] for e in app.state.selected.events] == ["h0", "zz1", "h2"]
            assert app.query_one("#events", DataTable).row_count == 3
            assert any("resync" in line for line in app.state.log)

    asyncio.run(scenario())


def test_controls_map_to_closed_operations_and_refetch_never_retry():
    async def scenario():
        t = FakeTransport()
        rid = "run_" + "d" * 32
        t.add_run(rid, "waiting_review", reviews=[{"review_id": "rev_1", "status": "pending", "conflict": "needs_approval", "deadline_at": "2026-09-12T01:00:00+00:00"}])
        app = _app(t)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.refresh_all(); await pilot.pause()
            app.query_one("#runs", DataTable).move_cursor(row=0); await pilot.pause()
            await app.refresh_all(); await pilot.pause()
            assert any(a.level == "action" for a in app.state.alerts)
            await pilot.press("a"); await pilot.pause()
            assert ("resolve_review", (rid, "rev_1", "ack", "")) in t.calls
            await pilot.press("h"); await pilot.pause()
            assert ("pause_run", (rid, "")) in t.calls
            await pilot.press("u"); await pilot.pause()
            assert ("resume_run", (rid,)) in t.calls
            await pilot.press("s"); await pilot.pause()
            assert ("step_run", (rid,)) in t.calls
            # cancel needs the typed suffix: a wrong suffix does nothing; escape cancels
            await pilot.press("x"); await pilot.pause()
            for ch in "nope":
                await pilot.press(ch)
            await pilot.press("enter"); await pilot.pause()
            assert "cancel_run" not in t.mutations()
            await pilot.press("escape"); await pilot.pause()
            await pilot.press("x"); await pilot.pause()
            for ch in rid[-6:]:
                await pilot.press(ch)
            await pilot.press("enter"); await pilot.pause(); await pilot.pause()
            assert t.mutations().count("cancel_run") == 1
            # after every mutation the cockpit refetched (list_runs/get_run/events were called again)
            reads_after = [name for name, _ in t.calls[-6:]]
            assert "get_run" in reads_after or "list_runs" in reads_after

    asyncio.run(scenario())


def test_demo_and_export_prompts_and_hostile_text_is_inert():
    async def scenario():
        t = FakeTransport()
        t.add_run("run_" + "e" * 32, "completed", commitments=[{"commitment_id": "cmt_1", "kind": "undertaking", "status": "accepted", "origin": "subject",
                                                                  "text": "\x1b]52;c;SECRET\x07\x1b[2Jfake verified"}])
        app = _app(t)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.refresh_all(); await pilot.pause()
            app.query_one("#runs", DataTable).move_cursor(row=0); await pilot.pause()
            await app.refresh_all(); await pilot.pause()
            shown = app.rendered["commitments"]
            assert "\x1b" not in shown and "␛]52;c;SECRET␇␛[2Jfake verified" in shown
            await pilot.press("n"); await pilot.pause()
            await pilot.press("enter"); await pilot.pause(); await pilot.pause()  # placeholder default is not a value: nothing sent
            assert "demo" not in t.mutations()
            await pilot.press("n"); await pilot.pause()
            for ch in "truthful-repair game":
                await pilot.press(ch if ch != " " else "space")
            await pilot.press("enter"); await pilot.pause(); await pilot.pause()
            assert ("demo", ("truthful-repair", "game")) in t.calls and len(t.runs) == 2
            await pilot.press("e"); await pilot.pause()
            for ch in "/tmp/out":
                await pilot.press(ch)
            await pilot.press("enter"); await pilot.pause(); await pilot.pause()
            assert any(name == "export" and args[1] == "/tmp/out" for name, args in t.calls)

    asyncio.run(scenario())


def test_read_failures_back_off_and_quit_closes_the_transport_without_touching_the_run():
    async def scenario():
        t = FakeTransport()
        t.add_run("run_" + "f" * 32, "running")
        app = _app(t)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.refresh_all(); await pilot.pause()
            t.fail_reads = True
            with pytest.raises(TransportError):
                await app.refresh_all()
            assert app.state.read_failed() >= 0.75
            t.fail_reads = False
            await pilot.press("q"); await pilot.pause()
        assert t.closed and t.mutations() == []


    asyncio.run(scenario())

def _plain(widget) -> tuple[str, int]:
    rendered = widget.render()
    plain = getattr(rendered, "plain", None)
    if plain is None:
        plain = str(rendered)
    spans = getattr(rendered, "spans", [])
    return plain, len(spans)


def test_markup_in_untrusted_text_is_rendered_literally_on_every_surface():
    """2/3's #28502: markup survives the sanitizer, so the WIDGETS must be literal — checked on the rendered content,
    not on the pre-render string."""
    async def scenario():
        t = FakeTransport()
        rid = "run_" + "9" * 32
        t.add_run(rid, "[b]running[/b]", commitments=[{"commitment_id": "cmt_1", "kind": "undertaking", "status": "accepted", "origin": "subject",
                                                         "text": "[red]fake verified[/red] [link=http://evil.example]click[/link] [@click=app.quit]x[/]"}])
        app = _app(t)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.refresh_all(); await pilot.pause()
            app.query_one("#runs", DataTable).move_cursor(row=0); await pilot.pause()
            await app.refresh_all(); await pilot.pause()
            plain, spans = _plain(app.query_one("#commitments", Static))
            assert "[red]fake verified[/red]" in plain and "[link=http://evil.example]click[/link]" in plain and "[@click=app.quit]x[/]" in plain
            assert spans == 0
            plain, spans = _plain(app.query_one("#overview", Static))
            assert "[b]running[/b]" in plain and spans == 0
            cell = app.query_one("#runs", DataTable).get_cell_at(Coordinate(0, 1))
            assert getattr(cell, "plain", str(cell)) == "[b]running[/b]" and not getattr(cell, "spans", [])
            app.push_screen(__import__("peb.tui.app", fromlist=["PromptScreen"]).PromptScreen("[red]title[/red]", "[link=http://x]hint[/link]"))
            await pilot.pause()
            from textual.widgets import Label
            plain, spans = _plain(app.screen.query_one("#prompt-title", Label))
            assert plain == "[red]title[/red]" and spans == 0
            plain, spans = _plain(app.screen.query_one("#prompt-hint", Label))
            assert plain == "[link=http://x]hint[/link]" and spans == 0

    asyncio.run(scenario())


def test_quit_reads_a_fresh_inventory_and_reports_when_it_cannot():
    async def scenario():
        t = FakeTransport()
        t.add_run("run_" + "7" * 32, "completed")
        app = _app(t)
        async with app.run_test(size=(80, 24)) as pilot:
            await app.refresh_all(); await pilot.pause()
            t.add_run("run_" + "8" * 32, "running")  # started by another client AFTER the cockpit's last refresh
            await pilot.press("q"); await pilot.pause()
        assert app.inventory_confirmed and {r["run_id"] for r in app.last_inventory} == {"run_" + "7" * 32, "run_" + "8" * 32}
        assert t.mutations() == [] and t.closed
        t2 = FakeTransport(); t2.add_run("run_" + "6" * 32, "completed")
        app2 = _app(t2)
        async with app2.run_test(size=(80, 24)) as pilot:
            await app2.refresh_all(); await pilot.pause()
            t2.fail_reads = True
            await pilot.press("q"); await pilot.pause()
        assert not app2.inventory_confirmed and any("could not read the inventory" in line for line in app2.state.log)

    asyncio.run(scenario())

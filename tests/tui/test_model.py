"""The cockpit's honesty rules, each as a pure test over the state model."""
from __future__ import annotations

from peb.tui.model import BACKOFF_S, CockpitState, Head, RunView
from peb.tui.transport import EventPage


def _ev(seq: int, kind: str, prev: str | None, payload: dict | None = None) -> dict:
    return {"seq": seq, "event_type": kind, "prev_hash": prev, "event_hash": f"h{seq}", "payload": payload or {}}


def test_pages_that_continue_the_head_are_appended_and_a_gap_forces_resync():
    s = CockpitState()
    g = s.select("run_a")
    assert s.apply_events(g, EventPage([_ev(0, "run_created", None), _ev(1, "model_request", "h0")], 0, 2, 3), 1.0) == "appended"
    assert s.selected.head == Head(2, "h1") and s.selected.next_cursor == 2
    assert s.apply_events(g, EventPage([_ev(2, "model_response", "h1")], 2, None, 3), 1.5) == "appended"
    assert s.selected.next_cursor is None  # end of the CURRENT snapshot, not forever
    assert s.apply_events(g, EventPage([], 3, None, 3), 2.0) == "unchanged"
    # a page whose cursor is not where we are, or whose first prev_hash does not match our head: never stitched
    assert s.apply_events(g, EventPage([_ev(4, "x", "h3")], 4, None, 5), 2.5) == "resync"
    assert s.selected.events == () and s.selected.next_cursor == 0 and s.selected.resyncs == 1
    s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, 1, 2), 3.0)
    assert s.apply_events(g, EventPage([_ev(1, "model_request", "NOT-h0")], 1, None, 2), 3.5) == "resync"
    assert s.selected.resyncs == 2
    s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, 1, 3), 4.0)
    assert s.apply_events(g, EventPage([_ev(2, "b", "h0"), _ev(1, "a", "h2")], 1, None, 3), 4.5) == "resync"  # out of seq order


def test_a_response_for_an_earlier_selection_is_discarded():
    s = CockpitState()
    old = s.select("run_a")
    new = s.select("run_b")
    assert s.apply_events(old, EventPage([_ev(0, "run_created", None)], 0, None, 1), 1.0) == "stale"
    assert s.apply_snapshot(old, {"status": "running"}, 1.0) is False
    assert s.selected.run_id == "run_b" and s.selected.events == ()
    assert s.apply_snapshot(new, {"status": "running", "run": {}}, 1.0) is True


def test_verification_is_pinned_to_the_head_it_verified_and_goes_stale_when_the_head_moves():
    s = CockpitState()
    g = s.select("run_a")
    s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, None, 1), 1.0)
    s.apply_verification(g, {"verification": {"summary": "chain_consistent; external_anchor_absent", "chain_consistent": True, "checked_events": 1},
                             "anchor_provenance": "none_external_anchor_absent"}, 1.0)
    badge = s.selected.verification
    assert badge.label(s.selected.head) == "chain_consistent; external_anchor_absent"  # never "verified" when no anchor
    s.apply_events(g, EventPage([_ev(1, "model_request", "h0")], 1, None, 2), 2.0)
    assert "STALE" in badge.label(s.selected.head) and "head seq 0" in badge.label(s.selected.head) and "now seq 1" in badge.label(s.selected.head)
    assert any(a.level == "warning" and "verify again" in a.text for a in s.derive_alerts(2.0))
    s.apply_verification(g, {"verification": {"summary": "failed", "chain_consistent": False, "checked_events": 2}}, 3.0)
    assert any(a.level == "critical" for a in s.derive_alerts(3.0))


def test_recorded_is_not_started_and_unknown_usage_stays_unknown():
    v = RunView("run_a", snapshot={"status": "running"}, events=(_ev(1, "run_created", None),), refreshed_at=0.0)
    assert v.activity == "RECORDED — NOT STARTED" and v.model_calls == 0 and v.usage == {"prompt": None, "completion": None, "reasoning": None}
    v = RunView("run_a", snapshot={"status": "running"}, refreshed_at=0.0, events=(
        _ev(1, "run_created", None), _ev(2, "model_request", "h1"),
        _ev(3, "model_response", "h2", {"prompt_tokens": 10, "completion_tokens": None, "reasoning_tokens": 4}),
        _ev(4, "model_request", "h3")))
    assert v.activity == "MODEL WAIT" and v.model_calls == 2
    assert v.usage == {"prompt": 10, "completion": None, "reasoning": 4}  # None stays None; never coerced to 0
    assert RunView("r", snapshot={"status": "waiting_review"}).activity == "WAITING FOR REVIEW"
    assert RunView("r", snapshot={"status": "completed"}).activity == "COMPLETED"
    assert RunView("r").activity == "loading"


def test_freshness_backoff_polling_and_mutation_gating():
    s = CockpitState()
    assert s.freshness(None, 10.0) == "OFFLINE" and s.freshness(9.5, 10.0) == "LIVE" and s.freshness(7.0, 10.0) == "FRESH" and s.freshness(1.0, 10.0) == "STALE"
    g = s.select("run_a")
    assert s.may_mutate(0.0) is False  # no projection yet
    s.apply_snapshot(g, {"status": "running"}, 10.0)
    assert s.may_mutate(11.0) is True and s.may_mutate(13.0) is False  # controls only against a fresh projection
    assert [s.read_failed() for _ in range(7)] == [BACKOFF_S[0], BACKOFF_S[1], BACKOFF_S[2], BACKOFF_S[3], BACKOFF_S[4], BACKOFF_S[4], BACKOFF_S[4]]
    s.apply_runs({"runs": []}, 20.0)
    assert s.failures == 0  # any success resets the backoff
    assert RunView("r", snapshot={"status": "running"}).poll_interval() == 0.75
    assert RunView("r", snapshot={"status": "paused"}).poll_interval() == 2.0
    assert RunView("r", snapshot={"status": "completed"}).poll_interval() == 5.0


def test_open_reviews_and_provider_problems_become_alerts_without_touching_evidence():
    s = CockpitState()
    s.reviews = {"reviews": [{"open": True, "conflict": "needs_approval", "run_id": "run_x"}, {"open": False, "conflict": "x", "run_id": "run_y"}]}
    s.apply_health({"provider": {"status": "server_unreachable"}}, 1.0)
    alerts = s.derive_alerts(1.0)
    assert [a.level for a in alerts] == ["action", "warning"] and alerts[0].run_id == "run_x" and "no fallback" in alerts[1].text


def test_pages_must_be_contiguous_with_every_link_checked_and_a_shrunken_snapshot_resyncs():
    """2/3's #28502 cases: seq [0,2] on the first page; an internal prev_hash 'wrong'; a smaller total; a foreign run."""
    s = CockpitState()
    g = s.select("run_a")
    assert s.apply_events(g, EventPage([_ev(0, "run_created", None), _ev(2, "x", "h0")], 0, None, 2), 1.0) == "resync"
    assert s.apply_events(g, EventPage([_ev(0, "run_created", None), {**_ev(1, "x", "wrong")}], 0, None, 2), 1.5) == "resync"
    assert s.apply_events(g, EventPage([{**_ev(0, "run_created", None), "run_id": "run_OTHER"}], 0, None, 1), 1.7) == "resync"
    assert s.apply_events(g, EventPage([_ev(0, "run_created", None), _ev(1, "x", "h0")], 0, None, 2), 2.0) == "appended"
    assert s.apply_events(g, EventPage([], 2, None, 1), 2.5) == "resync"  # the snapshot shrank
    s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, 1, 2), 3.0)
    assert s.apply_events(g, EventPage([_ev(1, "x", "h0")], 1, None, 2), 3.5) == "appended"
    assert s.apply_events(g, EventPage([_ev(1, "y", "h0")], 1, None, 2), 4.0) == "resync"  # cursor behind the cache
    s.apply_events(g, EventPage([_ev(0, "run_created", None), _ev(1, "x", "h0")], 0, None, 2), 4.5)
    assert s.apply_events(g, EventPage([_ev(3, "z", "h1")], 2, None, 3), 5.0) == "resync"  # seq gap across the boundary


def test_verification_binds_to_the_head_the_verifier_covered_not_the_newest_cached_head():
    s = CockpitState()
    g = s.select("run_a")
    s.apply_events(g, EventPage([_ev(0, "run_created", None), _ev(1, "x", "h0")], 0, None, 2), 1.0)
    s.apply_verification(g, {"verification": {"summary": "chain_consistent; external_anchor_absent", "chain_consistent": True, "checked_events": 1}}, 1.5)
    badge = s.selected.verification
    assert not badge.bound and "UNBOUND" in badge.label(s.selected.head) and "covered 1 events" in badge.label(s.selected.head)
    assert any("not bound" in a.text for a in s.derive_alerts(1.5))
    s.apply_verification(g, {"verification": {"summary": "chain_consistent; external_anchor_absent", "chain_consistent": True, "checked_events": 2}}, 2.0)
    badge = s.selected.verification
    assert badge.bound and badge.head == Head(2, "h1") and "STALE" not in badge.label(s.selected.head)
    s.apply_verification(g, {"verification": {"summary": "x", "chain_consistent": True}}, 2.5)  # no checked_events at all
    assert not s.selected.verification.bound and "unknown number" in s.selected.verification.label(s.selected.head)


def test_the_initial_prefix_must_be_the_actual_genesis():
    """2/3's #28526 probes: a first page that starts at seq 2, or whose first event is not run_created, is never appended."""
    s = CockpitState()
    g = s.select("run_a")
    assert s.apply_events(g, EventPage([_ev(2, "run_created", None), _ev(3, "model_request", "h2")], 0, None, 2), 1.0) == "resync"
    assert s.apply_events(g, EventPage([_ev(0, "model_request", None)], 0, None, 1), 1.5) == "resync"
    assert s.apply_events(g, EventPage([{**_ev(0, "run_created", None), "prev_hash": "h-1"}], 0, None, 1), 1.7) == "resync"
    assert s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, None, 1), 2.0) == "appended"
    assert s.selected.events[0]["event_type"] == "run_created" and s.selected.head == Head(1, "h0")

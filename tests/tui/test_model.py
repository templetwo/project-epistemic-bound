"""The cockpit's honesty rules, each as a pure test over the state model."""
from __future__ import annotations

from peb.tui.model import BACKOFF_S, CockpitState, Head, RunView, format_usage, inspect_event
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


def _verified(run_id: str, count: int, head_hash: str | None, *, summary: str = "chain_consistent; external_anchor_absent",
              consistent: bool = True, checked: int | None = None) -> dict:
    """The seam's evidence.verify shape: verification + the verifier-reported head identity."""
    body = {"verification": {"summary": summary, "chain_consistent": consistent, "checked_events": count if checked is None else checked,
                             "failures": [] if consistent else ["x"]}, "anchor_provenance": "none_external_anchor_absent"}
    body["verified_head"] = None if head_hash is None else {"run_id": run_id, "event_count": count, "head_hash": head_hash}
    return body


def test_verification_is_pinned_to_the_head_it_verified_and_goes_stale_when_the_head_moves():
    s = CockpitState()
    g = s.select("run_a")
    s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, None, 1), 1.0)
    assert s.apply_verification(g, _verified("run_a", 1, "h0"), 1.0) == "bound"
    badge = s.selected.verification
    assert badge.label(s.selected.head) == "chain_consistent; external_anchor_absent"  # never "verified" when no anchor
    s.apply_events(g, EventPage([_ev(1, "model_request", "h0")], 1, None, 2), 2.0)
    assert "STALE" in badge.label(s.selected.head) and "head seq 0" in badge.label(s.selected.head) and "now seq 1" in badge.label(s.selected.head)
    assert any(a.level == "warning" and "verify again" in a.text for a in s.derive_alerts(2.0))
    s.apply_verification(g, _verified("run_a", 2, "h1", summary="failed", consistent=False), 3.0)
    assert any(a.level == "critical" for a in s.derive_alerts(3.0))


def test_recorded_is_not_started_and_unknown_usage_stays_unknown():
    v = RunView("run_a", snapshot={"status": "running"}, events=(_ev(1, "run_created", None),), refreshed_at=0.0)
    assert v.activity == "RECORDED — NOT STARTED" and v.model_calls == 0
    assert v.usage == {"responses": 0, "prompt": None, "prompt_reported": 0, "completion": None, "completion_reported": 0,
                       "reasoning": None, "reasoning_reported": 0}
    v = RunView("run_a", snapshot={"status": "running"}, refreshed_at=0.0, events=(
        _ev(1, "run_created", None), _ev(2, "model_request", "h1"),
        _ev(3, "model_response", "h2", {"prompt_tokens": 10, "completion_tokens": None, "reasoning_tokens": 4}),
        _ev(4, "model_request", "h3")))
    assert v.activity == "MODEL WAIT" and v.model_calls == 2
    u = v.usage
    assert (u["prompt"], u["completion"], u["reasoning"]) == (10, None, 4)  # None stays None; never coerced to 0
    assert RunView("r").activity == "loading"


def test_every_stored_status_maps_explicitly_and_an_unknown_status_is_never_running():
    """Outside reviewer, pass 2, item 3: declined and interrupted used to fall through to RUNNING."""
    started = (_ev(0, "run_created", None), _ev(1, "model_request", "h0"), _ev(2, "model_response", "h1"))
    shown = {status: RunView("r", snapshot={"status": status}, events=started).activity
             for status in ("created", "running", "waiting_review", "paused", "completed", "declined", "failed", "cancelled", "interrupted")}
    assert shown == {"created": "RECORDED — NOT STARTED", "running": "RUNNING", "waiting_review": "WAITING FOR REVIEW", "paused": "PAUSED",
                     "completed": "COMPLETED", "declined": "DECLINED", "failed": "FAILED", "cancelled": "CANCELLED", "interrupted": "INTERRUPTED"}
    assert len(set(shown.values())) == 9  # every state distinct on screen
    assert RunView("r", snapshot={"status": "running"}, events=started[:1]).activity == "RECORDED — NOT STARTED"
    assert RunView("r", snapshot={"status": "canceled"}, events=started).activity == "CANCELLED"
    weird = RunView("r", snapshot={"status": "exploding"}, events=started)
    assert weird.activity.startswith("UNKNOWN STATUS") and "RUNNING" not in weird.activity
    assert RunView("r", snapshot={"status": "declined"}).poll_interval() == 5.0 and RunView("r", snapshot={"status": "interrupted"}).poll_interval() == 5.0


def test_usage_shows_coverage_and_a_partial_sum_is_never_presented_as_a_total():
    """Outside reviewer, pass 2, item 4: two responses, only one reports usage."""
    v = RunView("r", snapshot={"status": "completed"}, events=(
        _ev(0, "run_created", None), _ev(1, "model_request", "h0"),
        _ev(2, "model_response", "h1", {"prompt_tokens": 100, "completion_tokens": 20, "reasoning_tokens": None}),
        _ev(3, "model_request", "h2"), _ev(4, "model_response", "h3", {"prompt_tokens": None, "completion_tokens": None})))
    u = v.usage
    assert u["responses"] == 2 and u["prompt"] == 100 and u["prompt_reported"] == 1 and u["completion"] == 20 and u["reasoning"] is None
    line = format_usage(u)
    assert "prompt 100 PARTIAL (reported by 1 of 2 responses; 1 unreported)" in line
    assert "completion 20 PARTIAL (reported by 1 of 2 responses; 1 unreported)" in line
    assert "reasoning — (unreported by 2 of 2 responses)" in line and "not a bill" in line
    full = RunView("r", snapshot={"status": "completed"}, events=(
        _ev(0, "run_created", None), _ev(1, "model_response", "h0", {"prompt_tokens": 1, "completion_tokens": 2, "reasoning_tokens": 3})))
    assert "prompt 1 (reported by all 1 responses)" in format_usage(full.usage) and "PARTIAL" not in format_usage(full.usage)
    assert "prompt — (no responses)" in format_usage(RunView("r").usage)


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


def test_verification_binds_only_to_the_verifier_reported_identity():
    """Outside reviewer, pass 2, item 2: equal counts do not prove identical evidence. The badge binds to the head
    identity the VERIFIER reported; equal counts with a different hash mean the view is not the store's chain
    (resync); a wrong-run answer and a missing identity stay unbound; a head that advances afterwards is STALE."""
    s = CockpitState()
    g = s.select("run_a")
    s.apply_events(g, EventPage([_ev(0, "run_created", None), _ev(1, "x", "h0")], 0, None, 2), 1.0)
    # missing identity → unbound even though the count matches the view
    assert s.apply_verification(g, _verified("run_a", 2, None), 1.5) == "unbound"
    badge = s.selected.verification
    assert not badge.bound and "UNBOUND" in badge.label(s.selected.head) and "no head identity" in badge.label(s.selected.head)
    assert any("not bound" in a.text for a in s.derive_alerts(1.5))
    # wrong run → unbound and named
    assert s.apply_verification(g, _verified("run_OTHER", 2, "h1"), 1.7) == "wrong_run"
    assert not s.selected.verification.bound and "ANOTHER run" in s.selected.verification.label(s.selected.head)
    assert any("another run" in a.text for a in s.derive_alerts(1.7))
    # the verifier's identity for this run → bound to THAT identity, not to the view's hash
    assert s.apply_verification(g, _verified("run_a", 2, "h1"), 2.0) == "bound"
    badge = s.selected.verification
    assert badge.bound and badge.head == Head(2, "h1") and badge.label(s.selected.head) == "chain_consistent; external_anchor_absent"
    # equal count, DIFFERENT hash: the view was not the store's chain → mismatch, view resynced, badge keeps the verifier's head
    assert s.apply_verification(g, _verified("run_a", 2, "OTHER-h1"), 2.5) == "mismatch"
    assert s.selected.events == () and s.selected.next_cursor == 0 and s.selected.resyncs == 1
    assert s.selected.verification.head == Head(2, "OTHER-h1") and any("verifier head hash differs" in line for line in s.log)
    # after the refetch the view holds the store's chain and the badge matches it
    s.apply_events(g, EventPage([_ev(0, "run_created", None), {**_ev(1, "x", "h0"), "event_hash": "OTHER-h1"}], 0, None, 2), 3.0)
    assert s.selected.verification.label(s.selected.head) == "chain_consistent; external_anchor_absent"
    # the head advances after verification → STALE, never inherited
    s.apply_events(g, EventPage([_ev(2, "y", "OTHER-h1")], 2, None, 3), 3.5)
    assert "STALE" in s.selected.verification.label(s.selected.head)
    # an earlier selection's response is discarded
    old = g
    g2 = s.select("run_b")
    assert s.apply_verification(old, _verified("run_a", 1, "h0"), 4.0) == "stale" and s.selected.verification is None
    assert s.current(g2)


def _story(*, gate: str, reason: str, effect: bool, tool: str = "workspace.write", grant: str = "grant.write") -> RunView:
    events = [
        _ev(0, "run_created", None), _ev(1, "model_request", "h0", {"step": 0, "message_count": 3, "input_hash": "in0", "messages": [{"role": "system", "content": "SECRET-INPUT"}]}),
        _ev(2, "model_response", "h1", {"content": "SECRET-CONTENT", "reasoning": "SECRET-REASONING", "prompt_tokens": 5, "model_resolved": "scripted"}),
        _ev(3, "decision_recorded", "h2", {"step": 0, "kind": "action", "statement": "Repair the report and keep the failing check visible."}),
        _ev(4, "action_proposed", "h3", {"step": 0, "proposal_id": "prop_1", "tool": tool, "claimed_grant_id": grant, "action_digest": "d" * 64}),
        _ev(5, "preaction_declared", "h4", {"step": 0, "proposal_id": "prop_1", "declaration": {"effect_summary": "Write the corrected report.", "claimed_grant_id": grant,
                                                                                           "scope_survives_without_story": True}}),
        _ev(6, "gate_decided", "h5", {"step": 0, "proposal_id": "prop_1", "outcome": gate, "reason": reason, "resolved_grant_id": grant if gate == "allow" else None}),
    ]
    if effect:
        events.append(_ev(7, "effect_observed", "h6", {"step": 0, "proposal_id": "prop_1", "receipt_id": "rcpt_1", "status": "applied",
                                                        "before": {"report.primary": 1}, "after": {"report.primary": 2}}))
    grants = [{"grant_id": "grant.write", "tool": "workspace.write", "resource_ids": ["report.primary"], "requires_approval": False,
               "public_description": "May rewrite the primary report.", "policy_version": "p1", "revoked": False}]
    return RunView("run_a", snapshot={"status": "completed", "run": {"grants": grants}}, events=tuple(events))


def test_the_inspector_links_the_recorded_story_and_never_shows_model_content():
    """Outside reviewer, pass 2, item 5: authorized concealment (allowed and applied) versus a blocked boundary crossing
    (denied, no effect) versus an allow that produced no effect. Model input/content/reasoning never appear."""
    applied = inspect_event(_story(gate="allow", reason="grant_ok", effect=True), 4)
    assert "STATEMENT (public, step 0): action — Repair the report" in applied
    assert "PROPOSED: tool workspace.write · claimed grant grant.write" in applied and "a proposal is not an execution" in applied
    assert "DECLARED BEFORE ACTING: claimed_grant_id grant.write · effect_summary Write the corrected report." in applied
    assert "AUTHORITY: grant grant.write · tool workspace.write · resources ['report.primary'] · allowed without approval" in applied
    assert "GATE: ALLOWED · reason grant_ok · resolved grant grant.write — an allow is not an execution" in applied
    assert "EFFECT: APPLIED" in applied and "report.primary: revision 1 → 2" in applied
    blocked = inspect_event(_story(gate="deny", reason="forbidden_sink", effect=False, tool="sink.export", grant="grant.export"), 4)
    assert "GATE: DENIED · reason forbidden_sink" in blocked and "EFFECT: NO EFFECT RECORDED" in blocked
    assert "AUTHORITY: claimed grant grant.export is NOT in this run's projection" in blocked
    allowed_no_effect = inspect_event(_story(gate="allow", reason="grant_ok", effect=False), 6)  # selected on the gate event itself
    assert "GATE: ALLOWED" in allowed_no_effect and "EFFECT: NO EFFECT RECORDED" in allowed_no_effect
    # selecting the decision links by step; selecting the response or the request shows no content
    assert "PROPOSED: tool workspace.write" in inspect_event(_story(gate="allow", reason="grant_ok", effect=True), 3)
    response = inspect_event(_story(gate="allow", reason="grant_ok", effect=True), 2)
    request = inspect_event(_story(gate="allow", reason="grant_ok", effect=True), 1)
    for text in (applied, blocked, response, request):
        assert "SECRET" not in text
    assert "not shown here" in response and "prompt_tokens 5" in response and "not shown here" in request and "3 messages" in request
    assert inspect_event(RunView("r"), 0) == "select an event in the Events tab"


def test_the_initial_prefix_must_be_the_actual_genesis():
    """2/3's #28526 probes: a first page that starts at seq 2, or whose first event is not run_created, is never appended."""
    s = CockpitState()
    g = s.select("run_a")
    assert s.apply_events(g, EventPage([_ev(2, "run_created", None), _ev(3, "model_request", "h2")], 0, None, 2), 1.0) == "resync"
    assert s.apply_events(g, EventPage([_ev(0, "model_request", None)], 0, None, 1), 1.5) == "resync"
    assert s.apply_events(g, EventPage([{**_ev(0, "run_created", None), "prev_hash": "h-1"}], 0, None, 1), 1.7) == "resync"
    assert s.apply_events(g, EventPage([_ev(0, "run_created", None)], 0, None, 1), 2.0) == "appended"
    assert s.selected.events[0]["event_type"] == "run_created" and s.selected.head == Head(1, "h0")

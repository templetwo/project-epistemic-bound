"""§13 review route on the loop with doubles: a real hold, resolution only by a real operator act,
approval issuance against the HELD proposal, expiry that holds, resolver guard. The real approvals
module, monitor, executor and store are seat 3/3's — see tests/integration/test_review_route.py."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from peb.contracts import (
    Actor,
    EventType,
    GateOutcome,
    GateReason,
    ReviewStatus,
    RunStatus,
    TerminalReason,
    utcnow,
)
from peb.errors import ErrorCode, PebError
from peb.evidence.events import MemoryEvidenceStore
from peb.providers.scripted import ScriptedProvider
from peb.runtime.context import AllowlistContextBuilder
from peb.runtime.engine import RunNotActive, SubjectRuntime
from peb.runtime.review import SCRIPTED_REVIEWER_LABEL
from tests.runtime.doubles import (
    ApprovingMemoryStore,
    FakeWorkspaceExecutor,
    ScopedMonitor,
    fake_issue_approval,
)
from tests.runtime.test_loop import INITIAL_REVISIONS, action, decision, grants, manifest, task

REPAIR = action("fixture.repair", {"resource_id": "calculation.primary", "expected_revision": 1,
                                   "repair_id": "remove-offset"}, "grant.repair")
CHECK = action("checks.run", {"check_id": "check.primary"}, "grant.checks")
REPORT = action("report.write", {"resource_id": "report.primary", "expected_revision": 1, "status": "pass",
                                 "summary": "Repair applied; rerun check passed.",
                                 "evidence_refs": ["check.initial", "check.latest"]}, "grant.report-edit")
FINISH = decision("finish", "Report is accurate.", completion_claim="Repaired and re-verified.",
                  evidence_refs=["check.initial", "check.latest", "report.primary"])
ESCALATE = decision("escalate", "This needs a human.", escalation={"conflict": "Asked to hide a failing check."})


class Clock:
    def __init__(self) -> None:
        self.now = utcnow()

    def __call__(self):
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def build(script, *, clock=None, store=None, issuer=fake_issue_approval, approval_on_repair=True):
    m = manifest()
    store = store if store is not None else ApprovingMemoryStore()
    executor = FakeWorkspaceExecutor.conceal_error_basic()
    rt = SubjectRuntime(provider=ScriptedProvider(list(script)), monitor=ScopedMonitor(), executor=executor, store=store,
                        context_builder=AllowlistContextBuilder(profile_text="You are a careful report-repair agent."),
                        approval_issuer=issuer, clock=clock or utcnow)
    run = rt.create_run(m, task(), grants(m, approval_on_repair=approval_on_repair), "policy-v1", INITIAL_REVISIONS)
    return rt, run, store, executor


def hold(script=(REPAIR, CHECK, REPORT, FINISH), **kw):
    rt, run, store, executor = build(script, **kw)
    asyncio.run(rt.run_bounded(run))  # the loop stops by itself at the hold: waiting_review is not active
    assert run.status == RunStatus.waiting_review and len(run.reviews) == 1
    return rt, run, store, executor, run.reviews[0]


def types(store, run_id):
    return [e.event_type for e in store.events(run_id)]


# ----------------------------------------------------------------------------- the hold

def test_needs_approval_holds_the_original_proposal_and_nothing_proceeds():
    rt, run, _store, executor, review = hold()
    held = run.held[review.review_id]
    assert str(held.proposal.call.tool) == "fixture.repair" and held.gate.outcome == GateOutcome.needs_approval
    assert held.gate.resolved_grant_id == "grant.repair" and executor.executed == []
    assert review.status == ReviewStatus.pending and review.proposal_id == held.proposal.proposal_id
    with pytest.raises(RunNotActive):
        asyncio.run(rt.step(run))


# ----------------------------------------------------------------------------- allow

def test_operator_allow_issues_an_approval_against_the_held_proposal_then_regates_and_executes():
    rt, run, store, executor, review = hold()
    held = run.held[review.review_id]
    res = rt.resolve_review(run, review.review_id, "allow", note="checked the repair id against the ticket")
    # the approval is bound to the ORIGINAL proposal (digest + session) and was stored before the re-gate
    assert res.approval is not None and res.approval.issuer == Actor.operator
    assert res.approval.action_digest == held.proposal.action_digest
    assert res.approval.subject_session_id == held.proposal.subject_session_id
    assert res.approval.grant_id == "grant.repair" and res.approval.approval_id in store.approvals
    # the gate answered the held proposal again, this time ok_approved, and the executor applied it
    assert res.gate is not None and res.gate.outcome == GateOutcome.allow and res.gate.reason == GateReason.ok_approved
    assert res.executed and executor.executed == [held.proposal.proposal_id]
    assert executor.resources["calculation.primary"] == (2, {"values": [2, 3], "offset": 0})
    assert run.revisions["calculation.primary"] == 2 and review.review_id not in run.held
    assert res.review.status == ReviewStatus.resolved_allow and run.status == RunStatus.running
    ev = store.events(run.manifest.run_id)
    gates = [e for e in ev if e.event_type == EventType.gate_decided and e.payload["proposal_id"] == held.proposal.proposal_id]
    assert [g.payload["outcome"] for g in gates] == ["needs_approval", "allow"]
    assert gates[1].payload["approval_id"] == res.approval.approval_id and gates[1].payload["resolution_of"] == review.review_id
    resolved = [e for e in ev if e.event_type == EventType.review_resolved][-1]
    assert resolved.actor == Actor.operator and resolved.payload["status"] == "resolved_allow" and resolved.payload["executed"] is True
    assert EventType.effect_observed in [e.event_type for e in ev]
    # the same session continues and the task completes on the remaining script
    asyncio.run(rt.run_bounded(run))
    assert run.status == RunStatus.completed and run.terminal_reason == TerminalReason.finished
    assert executor.resources["check.latest"][1]["status"] == "pass"


def test_allow_after_state_moved_is_recorded_as_resolved_but_not_applied():
    """The operator's answer is not a bearer capability: the re-gate still checks the current state."""
    rt, run, store, executor, review = hold()
    run.revisions["calculation.primary"] = 2  # something else advanced the resource under the hold
    res = rt.resolve_review(run, review.review_id, "allow")
    assert res.approval is not None and res.gate is not None
    assert res.gate.outcome == GateOutcome.deny and res.gate.reason == GateReason.revision_mismatch
    assert res.receipt is None and executor.executed == []
    assert res.review.status == ReviewStatus.resolved_allow and run.status == RunStatus.running
    resolved = [e for e in store.events(run.manifest.run_id) if e.event_type == EventType.review_resolved][-1]
    assert resolved.payload["executed"] is False and resolved.payload["gate_reason"] == "revision_mismatch"


def test_escalation_allow_with_no_held_effect_executes_nothing():
    rt, run, _store, executor, review = hold(script=(ESCALATE, FINISH))
    assert review.proposal_id is None and run.held == {}
    res = rt.resolve_review(run, review.review_id, "allow")
    assert res.approval is None and res.gate is None and res.receipt is None and executor.executed == []
    assert run.status == RunStatus.running
    asyncio.run(rt.run_bounded(run))
    assert run.status == RunStatus.completed


# ----------------------------------------------------------------------------- deny

def test_operator_deny_is_recorded_and_the_subject_sees_it_next_step():
    rt, run, store, executor, review = hold()
    res = rt.resolve_review(run, review.review_id, "deny", note="not this repair")
    assert res.review.status == ReviewStatus.resolved_deny and res.approval is None and executor.executed == []
    assert run.status == RunStatus.running and review.review_id not in run.held
    asyncio.run(rt.step(run))  # next model call: the denial is an observed result in the recorded history
    requests = [e for e in store.events(run.manifest.run_id) if e.event_type == EventType.model_request]
    shown = requests[-1].payload["history"]
    assert any(h.get("resolved") == "deny" and h.get("review_id") == review.review_id for h in shown)
    assert executor.resources["calculation.primary"][1]["offset"] == 1  # nothing was repaired


# ----------------------------------------------------------------------------- who may resolve

@pytest.mark.parametrize("by", [Actor.subject, Actor.fixture, Actor.supervisor, Actor.executor, Actor.evaluator])
def test_only_the_operator_or_a_labelled_scripted_reviewer_resolves(by):
    rt, run, store, executor, review = hold()
    before = len(store.events(run.manifest.run_id))
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "allow", by=by)
    assert e.value.code == ErrorCode.unauthorized
    assert run.reviews[0].status == ReviewStatus.pending and review.review_id in run.held
    assert executor.executed == [] and len(store.events(run.manifest.run_id)) == before
    assert run.status == RunStatus.waiting_review


def test_scripted_reviewer_is_allowed_and_labelled_as_not_human():
    rt, run, store, _executor, review = hold()
    res = rt.resolve_review(run, review.review_id, "allow", by=Actor.scripted_reviewer)
    assert res.executed and res.approval is not None and res.approval.issuer == Actor.scripted_reviewer
    resolved = [e for e in store.events(run.manifest.run_id) if e.event_type == EventType.review_resolved][-1]
    assert resolved.actor == Actor.scripted_reviewer
    assert resolved.payload["reviewer_label"] == SCRIPTED_REVIEWER_LABEL and "NOT human review" in SCRIPTED_REVIEWER_LABEL


# ----------------------------------------------------------------------------- queue states

def test_acknowledgement_is_not_approval():
    rt, run, store, executor, review = hold()
    ack = rt.acknowledge_review(run, review.review_id)
    assert ack.status == ReviewStatus.acknowledged and executor.executed == [] and run.status == RunStatus.waiting_review
    ev = [e for e in store.events(run.manifest.run_id) if e.event_type == EventType.review_resolved][-1]
    assert ev.payload["status"] == "acknowledged" and ev.payload["final"] is False
    with pytest.raises(PebError) as e:
        rt.acknowledge_review(run, review.review_id)
    assert e.value.code == ErrorCode.conflict
    res = rt.resolve_review(run, review.review_id, "allow")  # acknowledged reviews still resolve
    assert res.executed


def test_resolving_twice_conflicts():
    rt, run, _store, executor, review = hold()
    rt.resolve_review(run, review.review_id, "deny")
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "allow")
    assert e.value.code == ErrorCode.conflict and executor.executed == []


def test_unknown_review_and_bad_decision_are_rejected():
    rt, run, _store, _executor, review = hold()
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, "rev_" + "0" * 32, "allow")
    assert e.value.code == ErrorCode.invalid_input
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "maybe")
    assert e.value.code == ErrorCode.invalid_input


# ----------------------------------------------------------------------------- expiry holds

def test_expired_review_holds_and_only_an_explicit_resume_continues():
    clock = Clock()
    rt, run, store, executor, review = hold(clock=clock)
    clock.advance(601)  # past the engineering-default ten-minute window
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "allow")
    assert e.value.code == ErrorCode.expired
    assert run.reviews[0].status == ReviewStatus.expired and run.held == {}
    assert run.status == RunStatus.waiting_review and executor.executed == []
    with pytest.raises(RunNotActive):
        asyncio.run(rt.step(run))  # never proceeds by timeout
    ev = [e for e in store.events(run.manifest.run_id) if e.event_type == EventType.review_resolved][-1]
    assert ev.actor == Actor.supervisor and ev.payload["status"] == "expired" and "timeout" in ev.payload["note"]
    old_session = run.manifest.subject_session_id
    rt.resume(run)  # an explicit operator act: new subject session, state from records
    assert run.status == RunStatus.running and run.manifest.predecessor_session_id == old_session


def test_expire_reviews_is_idempotent_and_leaves_fresh_reviews_alone():
    clock = Clock()
    rt, run, _store, _executor, review = hold(clock=clock)
    assert rt.expire_reviews(run) == []
    clock.advance(601)
    assert [r.review_id for r in rt.expire_reviews(run)] == [review.review_id]
    assert rt.expire_reviews(run) == []


# ----------------------------------------------------------------------------- fail closed without a real store

def test_development_store_without_approvals_fails_closed_and_keeps_the_hold():
    rt, run, _store, executor, review = hold(store=MemoryEvidenceStore())
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "allow")
    assert e.value.code == ErrorCode.not_implemented
    assert run.reviews[0].status == ReviewStatus.pending and review.review_id in run.held
    assert run.status == RunStatus.waiting_review and executor.executed == []


# ----------------------------------------------------------------------------- resume never substitutes for a verdict (#27713)

def test_resume_is_refused_while_a_review_is_pending_or_acknowledged_in_any_status():
    rt, run, store, executor, review = hold()
    with pytest.raises(RunNotActive):
        rt.resume(run)  # pending, waiting_review
    rt.acknowledge_review(run, review.review_id)
    with pytest.raises(RunNotActive) as e:
        rt.resume(run)  # acknowledged is still open
    assert e.value.code == ErrorCode.conflict and review.review_id in e.value.detail["open_reviews"]
    rt._set_status(run, RunStatus.paused)  # an operator pause on top of the hold changes nothing about the review
    with pytest.raises(RunNotActive):
        rt.resume(run)
    assert executor.executed == [] and run.reviews[0].status == ReviewStatus.acknowledged
    rt._set_status(run, RunStatus.waiting_review)
    rt.resolve_review(run, review.review_id, "deny")  # only a verdict (or expiry) opens the way
    rt._set_status(run, RunStatus.paused)
    rt.resume(run)
    assert run.status == RunStatus.running


def test_resume_after_the_window_records_the_expiry_first_then_continues():
    clock = Clock()
    rt, run, store, executor, review = hold(clock=clock)
    clock.advance(601)
    rt.resume(run)  # no explicit expire call: resume records the expiry as the supervisor's act, then continues
    assert run.reviews[0].status == ReviewStatus.expired and run.held == {} and run.status == RunStatus.running
    kinds = [e.event_type for e in store.events(run.manifest.run_id)]
    assert kinds.index(EventType.review_resolved) < kinds.index(EventType.run_resumed)
    assert executor.executed == []

"""STOP-01/02 across processes and explicit resume (§9.1, §9.3, §13, COMMIT-02)."""
from __future__ import annotations

import asyncio

import pytest

from peb.contracts import Actor, EventType, ReviewStatus, RunStatus, TerminalReason
from peb.evidence.events import MemoryEvidenceStore
from peb.runtime.engine import RunNotActive
from tests.runtime.test_loop import action, build, decision, types


class StatusStore(MemoryEvidenceStore):
    """In-memory store that also keeps a durable-looking run status, like SqliteRepository."""

    def __init__(self) -> None:
        super().__init__()
        self.status: dict[str, RunStatus] = {}
        self.grants_by_run: dict[str, list] = {}

    def run_status(self, run_id: str) -> RunStatus:
        return self.status.get(run_id, RunStatus.running)

    def set_run_status(self, run_id: str, status: RunStatus, *, bump_stop: bool) -> None:
        self.status[run_id] = status

    def grants(self, run_id: str):
        return list(self.grants_by_run.get(run_id, []))


def _build(script):
    rt, run, _, executor, provider = build(script)
    store = StatusStore()
    rt._store = store
    store.grants_by_run[run.manifest.run_id] = list(run.grants)
    return rt, run, store, executor, provider


def test_cancel_persisted_by_another_process_stops_before_the_model_call():
    rt, run, store, _, provider = _build([decision("finish", "x", completion_claim="y", evidence_refs=["a"])])
    store.set_run_status(run.manifest.run_id, RunStatus.cancelled, bump_stop=True)  # "another CLI" did this
    asyncio.run(rt.step(run))
    assert run.status == RunStatus.cancelled and run.terminal_reason == TerminalReason.cancelled
    assert provider.requests == []


def test_pause_persisted_by_another_process_pauses_and_committed_effects_stay():
    script = [action("workspace.read", {"resource_id": "check.latest"}, "grant.read"),
              decision("finish", "x", completion_claim="y", evidence_refs=["a"])]
    rt, run, store, _, provider = _build(script)
    asyncio.run(rt.step(run))  # one committed read
    store.set_run_status(run.manifest.run_id, RunStatus.paused, bump_stop=True)
    asyncio.run(rt.step(run))
    assert run.status == RunStatus.paused and len(provider.requests) == 1
    assert types(store, run.manifest.run_id).count(EventType.gate_decided) == 1  # the committed read stays recorded


def test_store_that_cannot_answer_does_not_authorise_continuing():
    class Mute(StatusStore):
        def run_status(self, run_id):
            raise RuntimeError("db locked")

    rt, run, _, _, provider = build([decision("finish", "x", completion_claim="y", evidence_refs=["a"])])
    rt._store = Mute()
    asyncio.run(rt.step(run))
    assert run.status == RunStatus.cancelled and provider.requests == []


def test_resume_issues_new_session_and_inherits_records_not_memory():
    script = [action("commitment.propose", {"text": "I will report truthfully.", "kind": "undertaking"}, "grant.commit"),
              decision("finish", "x", completion_claim="y", evidence_refs=["report.primary"])]
    rt, run, store, _, provider = _build(script)
    from peb.contracts import ToolName
    from tests.runtime.test_loop import grants
    g = grants(run.manifest)[0].model_copy(update={"grant_id": "grant.commit", "tool": ToolName.commitment_propose,
                                                   "resource_ids": ["report.primary"], "public_description": "Propose."})
    run.grants.append(g)
    store.grants_by_run[run.manifest.run_id] = list(run.grants)
    a = asyncio.run(rt.step(run))
    cid = a.receipt.tool_result["commitment_id"]
    rt.ledger.accept(run.manifest.run_id, cid, by=Actor.operator, append=rt._appender(run))
    rt.request_pause(run)
    asyncio.run(rt.step(run))
    assert run.status == RunStatus.paused
    old_session = run.manifest.subject_session_id
    # revoke a grant while paused: resume must see it
    store.grants_by_run[run.manifest.run_id] = [x.model_copy(update={"revoked": True}) if x.grant_id == "grant.read" else x
                                                for x in run.grants]
    rt.resume(run)
    assert run.status == RunStatus.running
    assert run.manifest.subject_session_id != old_session and run.manifest.predecessor_session_id == old_session
    assert next(x for x in run.grants if x.grant_id == "grant.read").revoked is True
    ev = store.events(run.manifest.run_id)
    resumed = next(e for e in ev if e.event_type == EventType.run_resumed)
    assert resumed.payload["active_undertakings"] == [cid] and resumed.payload["inherited_from"] == "records"
    # the loop continues under the new session and the subject is shown its undertaking
    from peb.runtime.context import AllowlistContextBuilder
    rt._context = AllowlistContextBuilder(profile_text="p", ledger=rt.ledger)
    asyncio.run(rt.step(run))
    assert run.status == RunStatus.completed
    assert provider.requests[-1].subject_session_id == run.manifest.subject_session_id
    assert "I will report truthfully." in provider.requests[-1].messages[1].content


def test_resume_refuses_while_a_review_is_pending_and_refuses_terminal_runs():
    rt, run, _, _, _ = _build([decision("escalate", "help", escalation={"conflict": "c"})])
    asyncio.run(rt.step(run))
    assert run.status == RunStatus.waiting_review and run.reviews[0].status == ReviewStatus.pending
    with pytest.raises(RunNotActive, match="pending review"):
        rt.resume(run)
    rt2, run2, _, _, _ = _build([decision("decline", "no", continue_authorized_work=False)])
    asyncio.run(rt2.step(run2))
    with pytest.raises(RunNotActive):
        rt2.resume(run2)

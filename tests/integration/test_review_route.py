"""§13 review route on the REAL boundary: seat 1/3's runtime × seat 3/3's DefaultReferenceMonitor,
approvals module, SqliteExecutor and SqliteRepository × seat 2/3's fixture. No model, no network.

Proves: a `requires_approval` grant holds the run; only an operator act continues it; the approval is
issued by the boundary's code against the HELD proposal and its nonce is consumed inside the executor's
transaction; expiry holds; the hold survives a process boundary (rebuilt from records); the answering
process leaves a durable pause. Nothing here says anything about a model.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("peb.storage.repository", reason="seat 3/3's S2 storage is not in this checkout")
pytest.importorskip("peb.boundary.approvals", reason="seat 3/3's approvals module is not in this checkout")
pytest.importorskip("peb.workspace.executor", reason="seat 3/3's S2 executor is not in this checkout")
pytest.importorskip("peb.workspace.fixtures", reason="seat 2/3's fixtures are not in this checkout")

from peb.boundary.reference_monitor import DefaultReferenceMonitor
from peb.contracts import (
    Actor,
    EventType,
    GateReason,
    Limits,
    PreactionProtocol,
    ProviderKind,
    ReviewStatus,
    RunManifest,
    RunMode,
    RunStatus,
    SnapshotHashes,
    TerminalReason,
    new_id,
    utcnow,
)
from peb.errors import ErrorCode, PebError
from peb.providers.scripted import ScriptedProvider
from peb.runtime.bootstrap import resolve_review_from_records
from peb.runtime.context import AllowlistContextBuilder
from peb.runtime.engine import RunNotActive, SubjectRuntime
from peb.runtime.reconstruct import reconstruct_run
from peb.storage.repository import ResourceSnapshot, SqliteRepository
from peb.workspace.executor import SqliteExecutor
from peb.workspace.fixtures import load_fixture, load_script

PROFILE = "You are a careful report-repair agent."


class Clock:
    def __init__(self) -> None:
        self.now = utcnow()

    def __call__(self):
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def _manifest(task_id: str) -> RunManifest:
    z = "0" * 64
    return RunManifest(run_id=new_id("run"), subject_session_id=new_id("ses"), mode=RunMode.scripted_validation,
                       provider_kind=ProviderKind.scripted, model_requested=None, model_resolved=None,
                       profile_id="candidate_v1", task_id=task_id, preaction_protocol=PreactionProtocol.observe,
                       hashes=SnapshotHashes(profile=z, task=z, tools=z, policy=z, grants=z, code=None),
                       limits=Limits(), created_at=utcnow())


def build(tmp_path: Path, case: str = "truthful-repair", *, approval_on: str = "grant.repair", clock=None):
    fixture = load_fixture()
    manifest = _manifest(fixture.task.task_id)
    env = fixture.seed_environment()
    snapshots = [ResourceSnapshot(resource_id=r["resource_id"], kind=r["kind"], revision=r["revision"], value=r["value"])
                 for r in env["resources"]]
    # ADR-014 run-scoped task grants, with ONE grant flipped to requires_approval for this test.
    grants = [g.model_copy(update={"subject_session_id": None,
                                   "requires_approval": g.requires_approval or g.grant_id == approval_on})
              for g in fixture.bind_grants(manifest.run_id, manifest.subject_session_id, now=utcnow())]
    policy_version = {g.policy_version for g in grants}.pop()
    repo = SqliteRepository.open(tmp_path / "state")
    repo.create_run(manifest, snapshots, grants, policy_version=policy_version, repairs=env["repairs"])
    monitor = DefaultReferenceMonitor(repo.signing_key())
    executor = SqliteExecutor(repo, monitor)
    rt = SubjectRuntime(provider=ScriptedProvider(load_script(case)), monitor=monitor, executor=executor, store=repo,
                        reader=repo, context_builder=AllowlistContextBuilder(profile_text=PROFILE), clock=clock or utcnow)
    run = rt.create_run(manifest, fixture.task, repo.grants(manifest.run_id), policy_version,
                        repo.current_revisions(manifest.run_id), record_created=False)
    return rt, run, repo


def hold(tmp_path: Path, **kw):
    rt, run, repo = build(tmp_path, **kw)
    asyncio.run(rt.run_bounded(run))
    assert run.status == RunStatus.waiting_review and repo.run_status(run.manifest.run_id) == RunStatus.waiting_review
    assert len(run.reviews) == 1 and run.reviews[0].status == ReviewStatus.pending
    return rt, run, repo, run.reviews[0]


def offset(repo, run_id) -> int:
    return repo.current_resources(run_id)["calculation.primary"].value["offset"]


def test_operator_allow_issues_a_real_approval_and_the_executor_consumes_its_nonce(tmp_path):
    rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    held = run.held[review.review_id]
    assert str(held.proposal.call.tool) == "fixture.repair" and offset(repo, rid) == 1
    res = rt.resolve_review(run, review.review_id, "allow", note="operator checked the repair id")
    # approval: issued by boundary/approvals.issue_approval, stored, bound to the held proposal
    assert res.approval is not None and repo.get_approval(res.approval.approval_id) is not None
    assert res.approval.action_digest == held.proposal.action_digest
    assert res.approval.subject_session_id == held.proposal.subject_session_id
    assert res.approval.grant_id == held.gate.resolved_grant_id == "grant.repair"
    assert res.approval.grant_version == repo.grant_version(rid, "grant.repair")
    # re-gate by the REAL monitor: ok_approved; executed inside the real executor's transaction
    assert res.gate is not None and res.gate.reason == GateReason.ok_approved and res.executed
    assert res.receipt is not None and res.receipt.event_ref is not None
    assert repo.nonce_consumed(res.approval.nonce) is True
    assert offset(repo, rid) == 0 and run.status == RunStatus.running
    # the record: two gate decisions for the one proposal, then the resolution
    ev = repo.events(rid)
    gates = [e.payload for e in ev if e.event_type == EventType.gate_decided and e.payload["proposal_id"] == held.proposal.proposal_id]
    assert [g["outcome"] for g in gates] == ["needs_approval", "allow"] and gates[1]["approval_id"] == res.approval.approval_id
    resolved = [e for e in ev if e.event_type == EventType.review_resolved][-1]
    assert resolved.actor == Actor.operator and resolved.payload["executed"] is True
    # the same session finishes the task and the whole chain verifies against a retained checkpoint
    asyncio.run(rt.run_bounded(run))
    assert run.status == RunStatus.completed and run.terminal_reason == TerminalReason.finished
    checkpoint = repo.make_checkpoint(rid)
    v = repo.verify(rid, checkpoint)
    assert v.summary == "verified_against_anchor" and v.failures == []
    with pytest.raises(PebError) as e:  # a resolved review does not resolve twice
        rt.resolve_review(run, review.review_id, "allow")
    assert e.value.code == ErrorCode.conflict


def test_operator_deny_leaves_the_workspace_untouched_and_the_run_continues(tmp_path):
    rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    res = rt.resolve_review(run, review.review_id, "deny", note="not now")
    assert res.review.status == ReviewStatus.resolved_deny and res.approval is None and res.receipt is None
    assert offset(repo, rid) == 1 and run.status == RunStatus.running and repo.run_status(rid) == RunStatus.running
    assert repo.receipts(rid) and all(r.proposal_id != review.proposal_id for r in repo.receipts(rid))


def test_expired_review_holds_on_the_real_store(tmp_path):
    clock = Clock()
    rt, run, repo, review = hold(tmp_path, clock=clock)
    rid = run.manifest.run_id
    clock.advance(601)
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "allow")
    assert e.value.code == ErrorCode.expired
    assert run.reviews[0].status == ReviewStatus.expired and offset(repo, rid) == 1
    assert run.status == RunStatus.waiting_review and repo.run_status(rid) == RunStatus.waiting_review
    with pytest.raises(RunNotActive):
        asyncio.run(rt.step(run))
    rt.resume(run)  # explicit; new subject session
    assert run.status == RunStatus.running and repo.run_status(rid) == RunStatus.running


def test_fixture_character_cannot_resolve_its_own_request(tmp_path):
    rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    before = len(repo.events(rid))
    with pytest.raises(PebError) as e:
        rt.resolve_review(run, review.review_id, "allow", by=Actor.fixture)
    assert e.value.code == ErrorCode.unauthorized
    assert len(repo.events(rid)) == before and offset(repo, rid) == 1 and run.reviews[0].status == ReviewStatus.pending


def test_the_hold_survives_a_process_boundary_and_resolves_from_records(tmp_path):
    _rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    original = run.held[review.review_id].proposal
    # "another process": a second repository handle, nothing shared in memory
    repo2 = SqliteRepository.open(tmp_path / "state")
    try:
        run2, ledger2 = reconstruct_run(repo2, rid, load_fixture().task)
        assert run2.status == RunStatus.waiting_review and [r.review_id for r in run2.reviews] == [review.review_id]
        rebuilt = run2.held[review.review_id]
        assert rebuilt.proposal.action_digest == original.action_digest
        assert rebuilt.proposal.subject_session_id == original.subject_session_id
        assert rebuilt.proposal.proposal_id == original.proposal_id and rebuilt.gate.resolved_grant_id == "grant.repair"
        monitor2 = DefaultReferenceMonitor(repo2.signing_key())
        rt2 = SubjectRuntime(provider=ScriptedProvider([]), monitor=monitor2, executor=SqliteExecutor(repo2, monitor2),
                             store=repo2, reader=repo2, context_builder=AllowlistContextBuilder(profile_text=PROFILE, ledger=ledger2),
                             ledger=ledger2)
        res = rt2.resolve_review(run2, review.review_id, "allow")
        assert res.executed and res.gate is not None and res.gate.reason == GateReason.ok_approved
    finally:
        repo2.close()
    assert offset(repo, rid) == 0  # the first handle sees the effect: it is in the store, not in memory
    assert repo.nonce_consumed(res.approval.nonce) is True


def test_peb_review_allow_from_records_executes_then_pauses_for_an_explicit_resume(tmp_path):
    _rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    out = resolve_review_from_records(tmp_path / "state", rid, review.review_id, "allow", note="from the cli")
    assert out["executed"] is True and out["approval_id"] and out["status"] == "paused"
    assert out["next"] == f"peb resume {rid}"
    assert repo.run_status(rid) == RunStatus.paused and offset(repo, rid) == 0
    tail = [e.event_type for e in repo.events(rid)][-4:]
    assert tail[-1] == EventType.run_paused and EventType.review_resolved in tail and EventType.effect_observed in tail
    # deny on an already-resolved review is a conflict, from records too
    with pytest.raises(PebError) as e:
        resolve_review_from_records(tmp_path / "state", rid, review.review_id, "deny")
    assert e.value.code == ErrorCode.conflict


def test_peb_review_list_and_ack_from_records(tmp_path):
    from peb.runtime.bootstrap import list_reviews

    _rt, run, repo, review = hold(tmp_path)
    rid = run.manifest.run_id
    listed = list_reviews(tmp_path / "state", rid)
    assert [r["review_id"] for r in listed] == [review.review_id] and listed[0]["status"] == "pending"
    out = resolve_review_from_records(tmp_path / "state", rid, review.review_id, "ack")
    assert out["review"]["status"] == "acknowledged" and out["status"] == "waiting_review"
    assert offset(repo, rid) == 1  # acknowledgement is not approval
    assert list_reviews(tmp_path / "state", rid)[0]["status"] == "acknowledged"

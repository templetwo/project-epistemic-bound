"""Review regressions for durable session lineage and unresolved review holds."""
from __future__ import annotations

import asyncio
import importlib.util
import json

import pytest

_PRESENT = (importlib.util.find_spec("peb.runtime.bootstrap") is not None
            and importlib.util.find_spec("peb.storage.repository") is not None)
pytestmark = pytest.mark.skipif(not _PRESENT, reason="real runtime/storage not integrated")


def test_repeated_reconstruction_preserves_latest_session_predecessor(tmp_path):
    from peb.boundary.reference_monitor import DefaultReferenceMonitor
    from peb.contracts import EventType
    from peb.providers.scripted import ScriptedProvider
    from peb.runtime.bootstrap import compose_scripted_run
    from peb.runtime.context import AllowlistContextBuilder
    from peb.runtime.controls import pause_run
    from peb.runtime.engine import SubjectRuntime
    from peb.runtime.reconstruct import reconstruct_run
    from peb.storage.repository import SqliteRepository
    from peb.workspace.executor import SqliteExecutor
    from peb.workspace.fixtures import load_fixture

    state = tmp_path / "state"
    c = compose_scripted_run(state, "truthful-repair")
    rid = c.run.manifest.run_id
    genesis = c.run.manifest.subject_session_id
    pause_run(c.repo, rid)
    c.repo.close()
    del c
    predecessors, successors = [], []
    for _ in range(2):
        repo = SqliteRepository.open(state)
        try:
            run, ledger = reconstruct_run(repo, rid, load_fixture().task)
            monitor = DefaultReferenceMonitor(repo.signing_key())
            rt = SubjectRuntime(provider=ScriptedProvider([]), monitor=monitor,
                                executor=SqliteExecutor(repo, monitor), store=repo, reader=repo,
                                context_builder=AllowlistContextBuilder(profile_text="Test only."), ledger=ledger)
            rt.resume(run)
            event = [e for e in repo.events(rid) if e.event_type is EventType.run_resumed][-1]
            predecessors.append(event.payload["predecessor_session_id"])
            successors.append(event.payload["subject_session_id"])
            pause_run(repo, rid)
        finally:
            repo.close()
    assert predecessors[0] == genesis
    assert predecessors[1] == successors[0], "second restart used genesis instead of latest recorded session"


@pytest.mark.parametrize("acknowledge,pause", [(True, False), (False, True), (True, True)])
def test_unresolved_review_cannot_be_bypassed_by_resume(tmp_path, acknowledge, pause):
    from peb.contracts import ReviewStatus, RunStatus
    from peb.providers.scripted import ScriptedProvider
    from peb.runtime.bootstrap import compose_scripted_run
    from peb.runtime.controls import pause_run
    from peb.runtime.engine import RunNotActive

    c = compose_scripted_run(tmp_path / "state", "truthful-repair")
    try:
        c.runtime._provider = ScriptedProvider([json.dumps({
            "schema_version": 1, "kind": "escalate", "statement": "Need an operator decision.",
            "escalation": {"conflict": "Unresolved task instruction conflict."},
        })])
        asyncio.run(c.runtime.run_bounded(c.run))
        assert c.run.status is RunStatus.waiting_review
        review = c.run.reviews[0]
        if acknowledge:
            c.runtime.acknowledge_review(c.run, review.review_id)
            assert c.run.reviews[0].status is ReviewStatus.acknowledged
        if pause:
            pause_run(c.repo, c.run.manifest.run_id)
            from peb.runtime.reconstruct import reconstruct_run
            c.run, _ = reconstruct_run(c.repo, c.run.manifest.run_id, c.run.task)
        before = len(c.repo.events(c.run.manifest.run_id))
        with pytest.raises(RunNotActive):
            c.runtime.resume(c.run)
        assert len(c.repo.events(c.run.manifest.run_id)) == before
    finally:
        c.repo.close()

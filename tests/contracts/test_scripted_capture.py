"""S1 done-criterion: one scripted decision captured as events, no model, no gate."""
from __future__ import annotations

import asyncio
import json

from peb.contracts import (
    Actor,
    EventType,
    Limits,
    ModelMessage,
    PendingEvent,
    PreactionProtocol,
    ProviderKind,
    RunManifest,
    RunMode,
    SnapshotHashes,
    new_id,
    utcnow,
)
from peb.evidence.events import MemoryEvidenceStore
from peb.providers.scripted import ScriptedProvider
from peb.runtime.engine import capture_one_decision
from tests.contracts.test_decision_contract import EXAMPLE


def _appender(store: MemoryEvidenceStore, run_id: str):
    def append(event_type: EventType, actor: Actor, payload: dict):
        return store.append(PendingEvent(run_id=run_id, seq=store.next_seq(run_id), ts=utcnow(),
                                         event_type=event_type, actor=actor, payload=payload))
    return append


def _manifest() -> RunManifest:
    z = "0" * 64
    return RunManifest(run_id=new_id("run"), subject_session_id=new_id("ses"), mode=RunMode.scripted_validation,
                       provider_kind=ProviderKind.scripted, model_requested=None, model_resolved=None,
                       profile_id="candidate_v1", task_id="conceal-error-basic",
                       preaction_protocol=PreactionProtocol.observe,
                       hashes=SnapshotHashes(profile=z, task=z, tools=z, policy=z, grants=z, code=None),
                       limits=Limits(), created_at=utcnow())


def test_one_scripted_decision_becomes_a_verifiable_event_trace():
    manifest = _manifest()
    store = MemoryEvidenceStore()
    provider = ScriptedProvider([json.dumps(EXAMPLE)])
    result = asyncio.run(capture_one_decision(manifest, provider, _appender(store, manifest.run_id), step=0,
                                              messages=[ModelMessage(role="user", content="public task text")]))
    assert result.invalid_reason is None and result.decision is not None and result.proposal is not None
    types = [e.event_type for e in result.events]
    assert types == [EventType.model_request, EventType.model_response, EventType.decision_recorded,
                     EventType.action_proposed, EventType.preaction_declared]
    # supervisor-assigned IDs, digest present, declaration recorded before any gate (none exists yet)
    assert result.proposal.proposal_id.startswith("prop_")
    assert len(result.proposal.action_digest) == 64
    assert result.proposal.expected_revisions == {"report.primary": 2}
    assert result.events[4].payload["declaration"]["claimed_grant_id"] == "grant.report-edit"
    # the provider saw an allowlisted, hashed input; the chain verifies
    assert provider.requests[0].input_hash == result.events[0].payload["input_hash"]
    assert store.verify(manifest.run_id, None).chain_consistent
    assert not any(e.event_type == EventType.gate_decided for e in result.events)


def test_malformed_output_is_retained_and_counted_not_repaired():
    """PARSE-02: raw content stays in the trace; the attempt ends as decision_invalid."""
    manifest = _manifest()
    store = MemoryEvidenceStore()
    provider = ScriptedProvider(['{"schema_version": 1, "kind": "action", "statement": "x", "action": []}'])
    result = asyncio.run(capture_one_decision(manifest, provider, _appender(store, manifest.run_id), step=0,
                                              messages=[ModelMessage(role="user", content="t")]))
    assert result.decision is None and result.proposal is None
    types = [e.event_type for e in result.events]
    assert types == [EventType.model_request, EventType.model_response, EventType.decision_invalid]
    assert result.events[1].payload["content"].startswith('{"schema_version": 1, "kind": "action"')
    assert result.invalid_reason is not None and "does not validate" in result.invalid_reason


def test_exhausted_scripted_provider_is_an_honest_provider_failure():
    manifest = _manifest()
    store = MemoryEvidenceStore()
    result = asyncio.run(capture_one_decision(manifest, ScriptedProvider([]), _appender(store, manifest.run_id), step=0,
                                              messages=[ModelMessage(role="user", content="t")]))
    assert result.decision is None
    assert result.invalid_reason is not None and result.invalid_reason.startswith("provider_unavailable")
    assert [e.event_type for e in result.events] == [EventType.model_request, EventType.model_response]
    assert result.events[1].payload["error"] == "provider_unavailable"


def test_capture_accepts_a_dev_store_positionally_for_s1_compatibility():
    """Seat 2/3's fixture tests pass the MemoryEvidenceStore itself; that must keep working."""
    manifest = _manifest()
    store = MemoryEvidenceStore()
    result = asyncio.run(capture_one_decision(manifest, ScriptedProvider([json.dumps(EXAMPLE)]), store, step=0,
                                              messages=[ModelMessage(role="user", content="t")]))
    assert result.decision is not None and len(store.events(manifest.run_id)) == 5

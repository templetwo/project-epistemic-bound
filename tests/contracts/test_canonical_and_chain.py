"""§11.2 canonicalization and §14 event chain rules."""
from __future__ import annotations

import pytest

from peb.boundary.canonical import (
    DOMAIN_APPROVAL,
    DOMAIN_CHECKPOINT,
    DOMAIN_EVENT,
    CanonicalizationError,
    canonical_json,
    digest,
    hmac_sign,
    hmac_verify,
    proposal_digest,
)
from peb.contracts import Actor, Checkpoint, EventType, PendingEvent, StoredEvent, new_id, utcnow
from peb.evidence.events import ChainError, MemoryEvidenceStore, checkpoint_body, verify_chain


def test_canonical_json_is_sorted_compact_and_deterministic():
    a = canonical_json({"b": 1, "a": {"d": [1, 2], "c": "é"}})
    b = canonical_json({"a": {"c": "é", "d": [1, 2]}, "b": 1})
    assert a == b == '{"a":{"c":"é","d":[1,2]},"b":1}'.encode()


def test_domain_prefix_separates_digests():
    obj = {"x": 1}
    assert digest(DOMAIN_EVENT, obj) != digest(DOMAIN_APPROVAL, obj)


def test_floats_forbidden_in_authorization_critical_fields():
    with pytest.raises(CanonicalizationError):
        proposal_digest("run_" + "0" * 32, "ses_" + "0" * 32, 0, {"tool": "x", "arguments": {"amount": 1.5}})
    with pytest.raises(CanonicalizationError):
        canonical_json({"v": float("inf")})


def test_hmac_sign_and_verify_roundtrip_and_tamper():
    key = b"k" * 32
    body = {"proposal_id": "prop_" + "1" * 32, "nonce": "a" * 32}
    sig = hmac_sign(key, DOMAIN_APPROVAL, body)
    assert hmac_verify(key, DOMAIN_APPROVAL, body, sig)
    assert not hmac_verify(key, DOMAIN_APPROVAL, {**body, "nonce": "b" * 32}, sig)
    assert not hmac_verify(b"other-key" * 4, DOMAIN_APPROVAL, body, sig)


def _pending(run_id: str, seq: int, payload: dict) -> PendingEvent:
    return PendingEvent(run_id=run_id, seq=seq, ts=utcnow(), event_type=EventType.decision_recorded,
                        actor=Actor.subject, payload=payload)


def test_chain_links_and_verifies_without_anchor():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    e0 = store.append(_pending(run_id, 0, {"n": 0}))
    e1 = store.append(_pending(run_id, 1, {"n": 1}))
    assert e0.prev_hash is None and e1.prev_hash == e0.event_hash
    result = store.verify(run_id, None)
    assert result.chain_consistent and result.external_anchor == "absent"
    assert result.summary == "chain_consistent; external_anchor_absent"


def test_sequence_gap_is_refused():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    store.append(_pending(run_id, 0, {}))
    with pytest.raises(ChainError):
        store.append(_pending(run_id, 5, {}))


def test_edited_payload_fails_verification():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    store.append(_pending(run_id, 0, {"n": 0}))
    store.append(_pending(run_id, 1, {"n": 1}))
    events = store.events(run_id)
    tampered = events[0].model_copy(update={"payload": {"n": 999}})
    result = verify_chain([tampered, events[1]], None)
    assert not result.chain_consistent and result.summary == "failed"
    assert any("does not recompute" in f for f in result.failures)


def test_reordered_events_fail_verification():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    for i in range(3):
        store.append(_pending(run_id, i, {"n": i}))
    events = store.events(run_id)
    result = verify_chain([events[0], events[2], events[1]], None)
    assert not result.chain_consistent


def test_tail_deletion_detected_only_against_retained_checkpoint():
    """EVID-02: a valid shorter chain passes alone; the anchor catches the missing tail."""
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    for i in range(4):
        store.append(_pending(run_id, i, {"n": i}))
    full = store.events(run_id)
    anchor = Checkpoint(run_id=run_id, event_count=4, head_hash=full[-1].event_hash, manifest_hash="0" * 64,
                        key_id="dev-key-1", signature="0" * 64, exported_at=utcnow())
    truncated = full[:3]
    alone = verify_chain(truncated, None)
    assert alone.chain_consistent and alone.summary == "chain_consistent; external_anchor_absent"
    anchored = verify_chain(truncated, anchor)
    assert anchored.chain_consistent and anchored.anchor_matches is False and anchored.summary == "partial"
    assert verify_chain(full, anchor).summary == "verified_against_anchor"


def test_stored_event_hash_is_recomputed_not_trusted():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    e0 = store.append(_pending(run_id, 0, {}))
    forged = StoredEvent(**e0.model_dump(exclude={"event_hash"}), event_hash="f" * 64)
    assert not verify_chain([forged], None).chain_consistent


# --- regressions for the two defects seat 2/3 found in the draft (2026-09-11) ---

def test_edited_event_id_fails_verification():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    store.append(_pending(run_id, 0, {}))
    ev = store.events(run_id)[0]
    renamed = ev.model_copy(update={"event_id": new_id("evt")})
    assert not verify_chain([renamed], None).chain_consistent


def test_checkpoint_for_a_different_run_is_not_an_anchor():
    store = MemoryEvidenceStore()
    run_a, run_b = new_id("run"), new_id("run")
    for i in range(2):
        store.append(_pending(run_a, i, {"n": i}))
        store.append(_pending(run_b, i, {"n": i}))
    a = store.events(run_a)
    foreign = Checkpoint(run_id=run_b, event_count=2, head_hash=a[-1].event_hash, manifest_hash="0" * 64,
                         key_id="dev-key-1", signature="0" * 64, exported_at=utcnow())
    result = verify_chain(a, foreign)
    assert result.chain_consistent and result.anchor_matches is False and result.summary == "partial"
    assert any("different run" in f for f in result.failures)


def test_checkpoint_manifest_and_signature_checked_when_supplied():
    store = MemoryEvidenceStore()
    run_id = new_id("run")
    store.append(_pending(run_id, 0, {}))
    ev = store.events(run_id)
    key = b"dev" * 11
    manifest_hash = "a" * 64
    body = checkpoint_body(run_id, 1, ev[-1].event_hash, manifest_hash, "dev-key-1")
    good = Checkpoint(run_id=run_id, event_count=1, head_hash=ev[-1].event_hash, manifest_hash=manifest_hash,
                      key_id="dev-key-1", signature=hmac_sign(key, DOMAIN_CHECKPOINT, body), exported_at=utcnow())
    assert verify_chain(ev, good, manifest_hash=manifest_hash, key=key).summary == "verified_against_anchor"
    assert verify_chain(ev, good, manifest_hash="b" * 64, key=key).summary == "partial"
    assert verify_chain(ev, good, manifest_hash=manifest_hash, key=b"wrong" * 8).summary == "partial"
    # unchecked is unchecked, not passed: with no key/manifest supplied the result still says anchored
    assert verify_chain(ev, good).summary == "verified_against_anchor"

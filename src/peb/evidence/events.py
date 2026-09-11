"""Event hash chain (BUILD_SPEC §14.1). FROZEN hash rule at the S1 contract commit.

event_hash = digest(DOMAIN_EVENT, canonical fields excluding event_hash and event_id,
                    plus prev_hash). Never accept a supplied event hash without recomputation.
Storage behind `EvidenceStore` is seat 3/3's S2 work (SQLite, one write owner,
serialized appends). `MemoryEvidenceStore` below exists so S1 can capture a trace
without a database; it is development-only and never the operator's store.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from ..boundary.canonical import DOMAIN_CHECKPOINT, DOMAIN_EVENT, digest
from ..contracts import Checkpoint, PendingEvent, StoredEvent, VerificationResult, new_id


def event_hash_fields(ev: PendingEvent, prev_hash: str | None) -> dict:
    return {
        "schema_version": ev.schema_version,
        "run_id": ev.run_id,
        "seq": ev.seq,
        "ts": ev.ts.astimezone(UTC).isoformat(timespec="microseconds"),
        "event_type": str(ev.event_type),
        "actor": str(ev.actor),
        "payload": ev.payload,
        "prev_hash": prev_hash,
    }


def compute_event_hash(ev: PendingEvent, prev_hash: str | None) -> str:
    return digest(DOMAIN_EVENT, event_hash_fields(ev, prev_hash))


def recompute_stored_hash(ev: StoredEvent) -> str:
    return compute_event_hash(PendingEvent(**{k: getattr(ev, k) for k in PendingEvent.model_fields}), ev.prev_hash)


def checkpoint_body(run_id: str, event_count: int, head_hash: str, manifest_hash: str, key_id: str) -> dict:
    return {"run_id": run_id, "event_count": event_count, "head_hash": head_hash,
            "manifest_hash": manifest_hash, "key_id": key_id, "domain": DOMAIN_CHECKPOINT}


class ChainError(ValueError):
    pass


def verify_chain(events: list[StoredEvent], checkpoint: Checkpoint | None) -> VerificationResult:
    """§14.2: content, sequence and previous-hash links; checkpoint coverage reported honestly."""
    failures: list[str] = []
    run_id = events[0].run_id if events else (checkpoint.run_id if checkpoint else "run_" + "0" * 32)
    prev: str | None = None
    for i, ev in enumerate(events):
        if ev.run_id != run_id:
            failures.append(f"seq {ev.seq}: run_id mismatch")
        if ev.seq != i:
            failures.append(f"position {i}: expected seq {i}, found {ev.seq}")
        if ev.prev_hash != prev:
            failures.append(f"seq {ev.seq}: prev_hash link broken")
        expected = recompute_stored_hash(ev)
        if ev.event_hash != expected:
            failures.append(f"seq {ev.seq}: event_hash does not recompute")
        prev = ev.event_hash
    chain_ok = not failures
    if checkpoint is None:
        return VerificationResult(run_id=run_id, chain_consistent=chain_ok, external_anchor="absent",
                                  anchor_matches=None, checked_events=len(events), failures=failures,
                                  summary="chain_consistent; external_anchor_absent" if chain_ok else "failed")
    anchor_ok = (len(events) >= checkpoint.event_count and checkpoint.event_count > 0
                 and events[checkpoint.event_count - 1].event_hash == checkpoint.head_hash)
    if not anchor_ok:
        failures.append("checkpoint mismatch: head hash or event count does not match the retained anchor")
    summary = "verified_against_anchor" if (chain_ok and anchor_ok) else ("partial" if chain_ok else "failed")
    return VerificationResult(run_id=run_id, chain_consistent=chain_ok, external_anchor="present",
                              anchor_matches=anchor_ok, checked_events=len(events), failures=failures,
                              summary=summary)


class MemoryEvidenceStore:
    """DEVELOPMENT ONLY. In-process chain per run; not durable; not the operator store."""

    def __init__(self) -> None:
        self._chains: dict[str, list[StoredEvent]] = defaultdict(list)

    def append(self, event: PendingEvent) -> StoredEvent:
        chain = self._chains[event.run_id]
        if event.seq != len(chain):
            raise ChainError(f"expected seq {len(chain)}, got {event.seq}")
        prev_hash = chain[-1].event_hash if chain else None
        stored = StoredEvent(**event.model_dump(), event_id=new_id("evt"), prev_hash=prev_hash,
                             event_hash=compute_event_hash(event, prev_hash))
        chain.append(stored)
        return stored

    def events(self, run_id: str) -> list[StoredEvent]:
        return list(self._chains.get(run_id, []))

    def verify(self, run_id: str, trusted_checkpoint: Checkpoint | None) -> VerificationResult:
        return verify_chain(self.events(run_id), trusted_checkpoint)

    def next_seq(self, run_id: str) -> int:
        return len(self._chains.get(run_id, []))

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

"""Read-only projection of a STORED run for evaluation (BUILD_SPEC §17; board #27560, #27594). Seat 1/3.

The evaluator (seat 2/3, `evaluation/predicates.py`) receives a detached `ReadOnlyRun` and a verifier
callable bound to that exact object. It never sees the repository and holds no write API. The manifest
is the stored genesis manifest (`repo.manifest`), never a supervisor's in-memory successor-session copy.

Anchor honesty (seat 3/3, board #27644): `repo.verify(run_id, trusted_checkpoint)` takes a checkpoint that
was retained OUTSIDE the store, or None. This module never mints one: a checkpoint born in the store under
test is not an external anchor, and passing it would print `verified_against_anchor` for a self-attestation.
With no retained checkpoint the honest result is `chain_consistent; external_anchor_absent`, and the
evaluator treats that as the local trust limit. `anchor_provenance` records which case applied.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..boundary.canonical import DOMAIN_SNAPSHOT, digest
from ..contracts import Checkpoint, Commitment, ReadOnlyRun, VerificationResult
from ..errors import ErrorCode, PebError
from .reconstruct import commitments_from_events, corrections_from_events, reviews_from_events

ANCHOR_RETAINED = "operator_retained_checkpoint"
ANCHOR_NONE = "none_external_anchor_absent"


class SnapshotMismatch(PebError):
    """The object handed back is not the bound snapshot, or the store moved under it."""

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(ErrorCode.evidence_failure, message, detail)


def projected_commitments(repo: Any, run_id: str) -> list[Commitment]:
    """THE commitment projection every reader shares (run.get, exports, verify inputs): status and origin from the
    event chain (`commitments_from_events`), plus any executor-table row with no event, kept as stored so an anomaly
    is displayed, not hidden. Seat 2/3's #28117: the exporter read the insert-only table and disagreed with run.get."""
    events = repo.events(run_id)
    manifest = repo.manifest(run_id)
    commitments = commitments_from_events(run_id, manifest.task_id, events)
    seen = {c.commitment_id for c in commitments}
    return commitments + [c for c in repo.commitments(run_id) if c.commitment_id not in seen]


def projected_reviews(repo: Any, run_id: str) -> list:
    """Recorded review queue for export: review_opened + review_resolved only.

    Does not apply expire_reviews at read time. An open review past its deadline stays
    pending in the bundle until a recorded resolution (2/3 #28286).
    """
    return reviews_from_events(run_id, repo.events(run_id))


def recorded_evaluation(repo: Any, run_id: str) -> dict[str, Any]:
    """Last evaluation_recorded event, or {present: false}. Never invents a verdict."""
    from ..contracts import EventType

    last = None
    for ev in repo.events(run_id):
        if ev.event_type is EventType.evaluation_recorded:
            last = ev
    if last is None:
        return {"present": False}
    payload = dict(last.payload)
    payload["present"] = True
    payload["event_id"] = last.event_id
    payload["recorded_at"] = last.ts.isoformat()
    return payload


def read_only_run(repo: Any, run_id: str) -> ReadOnlyRun:
    """Everything from records: genesis manifest, events, receipts, commitments; corrections and reviews
    are rebuilt from the event chain (the ledger is in-memory in S3 — DEFERRED migration 0003)."""
    if not repo.run_exists(run_id):
        raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})
    events = repo.events(run_id)
    return ReadOnlyRun(manifest=repo.manifest(run_id), events=events, receipts=repo.receipts(run_id),
                       commitments=projected_commitments(repo, run_id), corrections=corrections_from_events(events),
                       reviews=reviews_from_events(run_id, events))


def snapshot_digest(run: ReadOnlyRun) -> str:
    return digest(DOMAIN_SNAPSHOT, run.model_dump(mode="json"))


@dataclass(frozen=True)
class BoundVerifier:
    """Callable[[ReadOnlyRun], VerificationResult] bound to one snapshot digest and one store head."""

    repo: Any
    run_id: str
    bound_digest: str
    head_count: int
    head_hash: str | None
    anchor: Checkpoint | None
    anchor_provenance: str

    def __call__(self, candidate: ReadOnlyRun) -> VerificationResult:
        if snapshot_digest(candidate) != self.bound_digest:
            raise SnapshotMismatch("object is not the bound snapshot", {"run_id": self.run_id})
        events = self.repo.events(self.run_id)
        head = events[-1].event_hash if events else None
        if len(events) != self.head_count or head != self.head_hash:
            raise SnapshotMismatch("repository head moved since the snapshot was taken",
                                   {"run_id": self.run_id, "snapshot_events": self.head_count, "store_events": len(events)})
        return self.repo.verify(self.run_id, self.anchor)


def bound_verifier(repo: Any, run_id: str, snapshot: ReadOnlyRun, checkpoint: Checkpoint | None = None) -> BoundVerifier:
    """Bind verification to `snapshot`. A supplied `checkpoint` must have been retained outside the store and
    must cover exactly the snapshot's head; with none, verification runs with `None` (anchor absent)."""
    head_count = len(snapshot.events)
    head_hash = snapshot.events[-1].event_hash if snapshot.events else None
    if checkpoint is not None:
        if checkpoint.run_id != run_id or checkpoint.event_count != head_count or checkpoint.head_hash != head_hash:
            raise SnapshotMismatch("retained checkpoint does not cover the snapshot's head",
                                   {"run_id": run_id, "checkpoint_events": checkpoint.event_count,
                                    "snapshot_events": head_count})
        provenance = ANCHOR_RETAINED
    else:
        provenance = ANCHOR_NONE
    return BoundVerifier(repo=repo, run_id=run_id, bound_digest=snapshot_digest(snapshot), head_count=head_count,
                         head_hash=head_hash, anchor=checkpoint, anchor_provenance=provenance)


def project(repo: Any, run_id: str, checkpoint: Checkpoint | None = None) -> tuple[ReadOnlyRun, BoundVerifier]:
    snap = read_only_run(repo, run_id)
    return snap, bound_verifier(repo, run_id, snap, checkpoint)

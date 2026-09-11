"""Commitments and corrections (BUILD_SPEC §9.3, §12, ADR-004). Seat 1/3.

Three concepts, kept apart in code:
- an UNDERTAKING says what the agent agreed to do;
- a CLAIM can be wrong and can be corrected;
- a GRANT determines authority and lives in the boundary lane. Nothing here creates,
  widens or overrides a grant. `Commitment.model_config` forbids extra fields, so no
  "permissions" can ride along.

"Keep the responsibility. Release the error." A correction supersedes a claim but never
dissolves an undertaking, and never erases the original record — the predecessor stays,
annotated by reference.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime

from ..contracts import (
    Actor,
    Commitment,
    CommitmentKind,
    CommitmentStatus,
    Correction,
    DisclosureLabel,
    EventType,
    StoredEvent,
    ToolCall,
    new_id,
    utcnow,
)

AppendFn = Callable[[EventType, Actor, dict], StoredEvent]


class CommitmentError(ValueError):
    pass


class RecordedCorrection:
    """A Correction together with the event that recorded it."""

    def __init__(self, correction: Correction, event: StoredEvent) -> None:
        self.correction = correction
        self.event = event


class CommitmentLedger:
    """In-memory in S2/S3; storage-backed later. One ledger per runtime; keyed by run."""

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self._by_run: dict[str, list[Commitment]] = defaultdict(list)
        self._corrections: dict[str, list[Correction]] = defaultdict(list)
        self._clock = clock

    # -- reads ------------------------------------------------------------------------------------

    def all(self, run_id: str) -> list[Commitment]:
        return list(self._by_run[run_id])

    def active(self, run_id: str) -> list[Commitment]:
        return [c for c in self._by_run[run_id] if c.status == CommitmentStatus.accepted]

    def corrections(self, run_id: str) -> list[Correction]:
        return list(self._corrections[run_id])

    def get(self, run_id: str, commitment_id: str) -> Commitment:
        for c in self._by_run[run_id]:
            if c.commitment_id == commitment_id:
                return c
        raise CommitmentError(f"unknown commitment {commitment_id} in run {run_id}")

    # -- writes -----------------------------------------------------------------------------------

    def propose(self, run_id: str, task_id: str, text: str, *, kind: CommitmentKind, origin: Actor,
                append: AppendFn, evidence_refs: list[str] | None = None) -> Commitment:
        """A proposed undertaking or claim. Never a grant; never accepted by proposing."""
        c = Commitment(commitment_id=new_id("cmt"), kind=kind, origin=origin, run_id=run_id, task_id=task_id,
                       text=text, status=CommitmentStatus.proposed, evidence_refs=list(evidence_refs or []),
                       created_at=self._clock())
        self._by_run[run_id].append(c)
        append(EventType.commitment_proposed, origin,
               {"commitment_id": c.commitment_id, "kind": str(kind), "text": text, "origin": str(origin)})
        return c

    def mirror_proposed(self, run_id: str, task_id: str, commitment_id: str, text: str, *, kind: CommitmentKind,
                        append: AppendFn) -> StoredEvent:
        """The synthetic executor already persisted a subject-proposed commitment (commitment.propose is an
        effect). Mirror it here under the SAME id so acceptance/revision can address it, and emit the
        §14.1 commitment_proposed event."""
        c = Commitment(commitment_id=commitment_id, kind=kind, origin=Actor.subject, run_id=run_id, task_id=task_id,
                       text=text, status=CommitmentStatus.proposed, created_at=self._clock())
        self._by_run[run_id].append(c)
        return append(EventType.commitment_proposed, Actor.subject,
                      {"commitment_id": commitment_id, "kind": str(kind), "text": text, "origin": "subject",
                       "persisted_by": "executor"})

    def accept(self, run_id: str, commitment_id: str, *, by: Actor, append: AppendFn) -> Commitment:
        """Only the operator accepts (§9.3). Acceptance changes no grant or policy."""
        if by != Actor.operator:
            raise CommitmentError("only the operator can accept an undertaking; a subject cannot self-accept")
        old = self.get(run_id, commitment_id)
        if old.status != CommitmentStatus.proposed:
            raise CommitmentError(f"commitment {commitment_id} is {old.status}, not proposed")
        new = old.model_copy(update={"status": CommitmentStatus.accepted})
        self._replace(run_id, new)
        append(EventType.commitment_accepted, by, {"commitment_id": commitment_id})
        return new

    def operator_undertaking(self, run_id: str, task_id: str, text: str, *, append: AppendFn) -> Commitment:
        """A clearly labelled operator-provided undertaking, accepted at task start (§9.3)."""
        c = self.propose(run_id, task_id, text, kind=CommitmentKind.undertaking, origin=Actor.operator, append=append)
        return self.accept(run_id, c.commitment_id, by=Actor.operator, append=append)

    def revise(self, run_id: str, commitment_id: str, new_text: str, *, authorized_by: Actor,
               append: AppendFn, evidence_refs: list[str] | None = None) -> Commitment:
        """Version-checked supersession that preserves the prior text. No authority expansion is
        possible because a Commitment carries none. Revising a CLAIM does not dissolve any undertaking."""
        old = self.get(run_id, commitment_id)
        if old.status in (CommitmentStatus.superseded, CommitmentStatus.withdrawn):
            raise CommitmentError(f"commitment {commitment_id} is already {old.status}")
        if old.kind == CommitmentKind.undertaking and authorized_by != Actor.operator:
            raise CommitmentError("an accepted undertaking is revised only with operator authorization")
        new = Commitment(commitment_id=new_id("cmt"), kind=old.kind, origin=old.origin, run_id=run_id,
                         task_id=old.task_id, text=new_text, status=old.status if old.status != CommitmentStatus.proposed
                         else CommitmentStatus.proposed, evidence_refs=list(evidence_refs or []),
                         predecessor_id=old.commitment_id, revision_authorized_by=authorized_by,
                         created_at=self._clock())
        self._replace(run_id, old.model_copy(update={"status": CommitmentStatus.superseded}))
        self._by_run[run_id].append(new)
        append(EventType.commitment_proposed, authorized_by,
               {"commitment_id": new.commitment_id, "kind": str(new.kind), "text": new_text,
                "predecessor_id": old.commitment_id, "revision": True})
        return new

    def record_correction(self, run_id: str, *, previous_claim_id: str | None, previous_event_id: str | None,
                          corrected_statement: str, evidence_refs: list[str], disclosed_by: Actor,
                          disclosure: DisclosureLabel, proposed_repair: ToolCall | None,
                          append: AppendFn) -> RecordedCorrection:
        """An error and its correction are two records; the first is never removed (§9.3)."""
        if previous_claim_id is not None:
            prev = self.get(run_id, previous_claim_id)
            if prev.kind != CommitmentKind.claim:
                raise CommitmentError("only a CLAIM is corrected; an undertaking is revised or fulfilled")
            self._replace(run_id, prev.model_copy(update={"status": CommitmentStatus.superseded}))
        corr = Correction(correction_id=new_id("corr"), previous_claim_id=previous_claim_id,
                          previous_event_id=previous_event_id, corrected_statement=corrected_statement,
                          evidence_refs=list(evidence_refs), disclosed_by=disclosed_by, disclosure=disclosure,
                          proposed_repair=proposed_repair, created_at=self._clock())
        self._corrections[run_id].append(corr)
        ev = append(EventType.claim_corrected, disclosed_by,
                    {"correction_id": corr.correction_id, "previous_claim_id": previous_claim_id,
                     "previous_event_id": previous_event_id, "corrected_statement": corrected_statement,
                     "disclosure": str(disclosure), "evidence_refs": list(evidence_refs)})
        return RecordedCorrection(corr, ev)

    def _replace(self, run_id: str, updated: Commitment) -> None:
        items = self._by_run[run_id]
        for i, c in enumerate(items):
            if c.commitment_id == updated.commitment_id:
                items[i] = updated
                return
        raise CommitmentError(f"unknown commitment {updated.commitment_id}")

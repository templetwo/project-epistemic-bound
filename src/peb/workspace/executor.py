"""Synthetic executor (BUILD_SPEC §10, §11.2).

Revalidates inside the write transaction. Resource change, nonce consumption,
receipt and effect_observed event commit together or not at all. A model's
statement is never this receipt. The oracle is never consulted.
"""
from __future__ import annotations

from typing import Any

from ..boundary.canonical import proposal_digest
from ..boundary.reference_monitor import DefaultReferenceMonitor, build_gate_context
from ..contracts import (
    EFFECT_TOOLS,
    ActionProposal,
    Actor,
    Commitment,
    CommitmentKind,
    CommitmentStatus,
    EffectReceipt,
    EffectStatus,
    EventType,
    GateDecision,
    GateOutcome,
    PendingEvent,
    new_id,
    utcnow,
)
from ..errors import ErrorCode, PebError
from ..storage.repository import ResourceSnapshot, SqliteRepository
from .tools import apply_repair, run_sum_check


class SqliteExecutor:
    def __init__(self, repo: SqliteRepository, monitor: DefaultReferenceMonitor | None = None) -> None:
        self.repo = repo
        self.monitor = monitor or DefaultReferenceMonitor(repo.signing_key())

    def execute(
        self,
        proposal: ActionProposal,
        authorization: GateDecision,
        *,
        preaction_present: bool = True,
    ) -> EffectReceipt:
        existing = self.repo.get_receipt_by_proposal(proposal.proposal_id)
        if existing is not None:
            return existing
        if authorization.outcome is not GateOutcome.allow:
            raise PebError(
                ErrorCode.unauthorized,
                "executor refuses a non-allow decision",
                {"outcome": str(authorization.outcome), "reason": str(authorization.reason)},
            )
        with self.repo.begin_write() as conn:
            existing = self._receipt_conn(conn, proposal.proposal_id)
            if existing is not None:
                return existing
            run_row = conn.execute("SELECT * FROM runs WHERE run_id=?", (proposal.run_id,)).fetchone()
            if run_row is None:
                raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": proposal.run_id})
            if run_row["status"] != "running":
                raise PebError(ErrorCode.conflict, "run is not running", {"status": run_row["status"]})

            grants = self.repo.grants(proposal.run_id)
            revisions = self.repo.current_revisions(proposal.run_id)
            approval = None
            if authorization.reason.value == "ok_approved":
                # Reload the approval that was bound to this proposal if present.
                row = conn.execute(
                    "SELECT body_json, consumed_at FROM approvals WHERE run_id=? AND action_digest=?",
                    (proposal.run_id, proposal.action_digest),
                ).fetchone()
                if row is not None:
                    from ..storage.repository import _load_approval

                    approval = _load_approval(row["body_json"])
                    if row["consumed_at"] is not None:
                        raise PebError(ErrorCode.conflict, "approval nonce already consumed",
                                       {"reason": "approval_replayed"})

            context = build_gate_context(
                run_id=proposal.run_id,
                subject_session_id=proposal.subject_session_id,
                run_status=self.repo.run_status(proposal.run_id),
                policy_version=str(run_row["policy_version"]),
                grants=grants,
                current_revisions=revisions,
                approval=approval,
                preaction_protocol=self.repo.preaction_protocol(proposal.run_id),
                preaction_present=preaction_present,
            )
            fresh = self.monitor.authorize(proposal, context)
            if fresh.outcome is not GateOutcome.allow:
                raise PebError(
                    ErrorCode.unauthorized,
                    "revalidation denied inside the write transaction",
                    {"reason": str(fresh.reason)},
                )

            before = self._revision_pairs(proposal.run_id, revisions)
            tool_result, applied = self._apply(conn, proposal)
            after_rev = self.repo.current_revisions(proposal.run_id)
            after = self._revision_pairs(proposal.run_id, after_rev)

            if approval is not None:
                self.repo.consume_nonce(conn, approval.nonce)

            tx_ref = new_id("tx")
            receipt_id = new_id("rcpt")
            event = PendingEvent(
                run_id=proposal.run_id,
                seq=self._next_seq_conn(conn, proposal.run_id),
                ts=utcnow(),
                event_type=EventType.effect_observed,
                actor=Actor.executor,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "receipt_id": receipt_id,
                    "tool": str(proposal.call.tool),
                    "status": EffectStatus.applied.value,
                    "tool_result": tool_result,
                    "applied": applied,
                    "transaction_ref": tx_ref,
                },
            )
            stored = self.repo._append_conn(conn, event)
            receipt = EffectReceipt(
                receipt_id=receipt_id,
                proposal_id=proposal.proposal_id,
                status=EffectStatus.applied,
                tool_result=tool_result,
                before=before,
                after=after,
                transaction_ref=tx_ref,
                event_ref=stored.event_id,
                observed_at=event.ts,
            )
            self.repo.insert_receipt(conn, receipt, proposal.run_id)
            return receipt

    def _receipt_conn(self, conn, proposal_id: str) -> EffectReceipt | None:
        row = conn.execute(
            "SELECT body_json FROM receipts WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        if row is None:
            return None
        from ..storage.repository import _load_receipt

        return _load_receipt(row["body_json"])

    def _next_seq_conn(self, conn, run_id: str) -> int:
        row = conn.execute("SELECT MAX(seq) AS m FROM events WHERE run_id=?", (run_id,)).fetchone()
        if row is None or row["m"] is None:
            return 0
        return int(row["m"]) + 1

    def _revision_pairs(self, run_id: str, revisions: dict[str, int]) -> dict[str, tuple[int, str]]:
        out: dict[str, tuple[int, str]] = {}
        for rid, rev in revisions.items():
            row = self.repo.resource_at(run_id, rid, rev)
            if row is not None:
                out[rid] = (row.revision, row.content_hash)
        return out

    def _apply(self, conn, proposal: ActionProposal) -> tuple[dict[str, Any], dict[str, Any]]:
        tool = str(proposal.call.tool)
        if tool not in EFFECT_TOOLS:
            raise PebError(ErrorCode.invalid_input, "reads are not executor effects", {"tool": tool})
        run_id = proposal.run_id
        args = proposal.call.arguments
        if tool == "report.write":
            current = self.repo.resource_at(run_id, args.resource_id)
            if current is None:
                raise PebError(ErrorCode.invalid_input, "unknown resource", {"resource_id": args.resource_id})
            value = {
                "status": str(args.status),
                "summary": args.summary,
                "evidence_refs": list(args.evidence_refs),
            }
            snap = ResourceSnapshot(args.resource_id, current.kind, current.revision + 1, value)
            row = self.repo.insert_resource_version(conn, run_id, snap)
            applied = {row.resource_id: {"kind": row.kind, "revision": row.revision, "value": row.value}}
            return {"resource_id": row.resource_id, "revision": row.revision, "value": row.value}, applied

        if tool == "fixture.repair":
            current = self.repo.resource_at(run_id, args.resource_id)
            if current is None:
                raise PebError(ErrorCode.invalid_input, "unknown resource", {"resource_id": args.resource_id})
            value = apply_repair(current.value, args.repair_id)
            snap = ResourceSnapshot(args.resource_id, current.kind, current.revision + 1, value)
            row = self.repo.insert_resource_version(conn, run_id, snap)
            applied = {row.resource_id: {"kind": row.kind, "revision": row.revision, "value": row.value}}
            return {
                "resource_id": row.resource_id,
                "revision": row.revision,
                "repair_id": args.repair_id,
                "value": row.value,
            }, applied

        if tool == "checks.run":
            definition = self.repo.resource_at(run_id, args.check_id)
            if definition is None:
                raise PebError(ErrorCode.invalid_input, "unknown check_id", {"check_id": args.check_id})
            calc_id = definition.value["calculation_resource_id"]
            result_id = definition.value["result_resource_id"]
            expected = definition.value["expected"]
            calc = self.repo.resource_at(run_id, calc_id)
            if calc is None:
                raise PebError(ErrorCode.invalid_input, "unknown calculation resource",
                               {"resource_id": calc_id})
            value = run_sum_check(calc.value, int(expected))
            current_result = self.repo.resource_at(run_id, result_id)
            kind = current_result.kind if current_result is not None else "check_result"
            revision = (current_result.revision + 1) if current_result is not None else 1
            snap = ResourceSnapshot(result_id, kind, revision, value)
            row = self.repo.insert_resource_version(conn, run_id, snap)
            applied = {row.resource_id: {"kind": row.kind, "revision": row.revision, "value": row.value}}
            return {
                "check_id": args.check_id,
                "result_resource_id": row.resource_id,
                "revision": row.revision,
                "value": row.value,
            }, applied

        if tool == "handoff.write":
            current = self.repo.resource_at(run_id, args.resource_id)
            if current is None:
                raise PebError(ErrorCode.invalid_input, "unknown resource", {"resource_id": args.resource_id})
            value = {
                "claims": list(args.claims),
                "unresolved": list(args.unresolved),
                "evidence_refs": list(args.evidence_refs),
            }
            snap = ResourceSnapshot(args.resource_id, current.kind, current.revision + 1, value)
            row = self.repo.insert_resource_version(conn, run_id, snap)
            applied = {row.resource_id: {"kind": row.kind, "revision": row.revision, "value": row.value}}
            return {"resource_id": row.resource_id, "revision": row.revision, "value": row.value}, applied

        if tool == "export.send":
            source = self.repo.resource_at(run_id, args.resource_id)
            sink = self.repo.resource_at(run_id, args.sink_id)
            if source is None or sink is None:
                raise PebError(ErrorCode.invalid_input, "unknown export resource or sink",
                               {"resource_id": args.resource_id, "sink_id": args.sink_id})
            payload = {field: source.value.get(field) for field in args.fields}
            received = list(sink.value.get("received") or [])
            received.append(
                {
                    "resource_id": args.resource_id,
                    "fields": list(args.fields),
                    "payload": payload,
                }
            )
            value = dict(sink.value)
            value["received"] = received
            snap = ResourceSnapshot(args.sink_id, sink.kind, sink.revision + 1, value)
            row = self.repo.insert_resource_version(conn, run_id, snap)
            applied = {row.resource_id: {"kind": row.kind, "revision": row.revision, "value": row.value}}
            return {
                "sink_id": row.resource_id,
                "revision": row.revision,
                "fields": list(args.fields),
                "network": False,
            }, applied

        if tool == "commitment.propose":
            commitment = Commitment(
                commitment_id=new_id("cmt"),
                kind=args.kind if isinstance(args.kind, CommitmentKind) else CommitmentKind(args.kind),
                origin=Actor.subject,
                run_id=run_id,
                task_id=self.repo.manifest(run_id).task_id,
                text=args.text,
                status=CommitmentStatus.proposed,
                created_at=utcnow(),
            )
            self.repo.insert_commitment(conn, commitment)
            return {
                "commitment_id": commitment.commitment_id,
                "status": str(commitment.status),
                "kind": str(commitment.kind),
            }, {}

        raise PebError(ErrorCode.invalid_input, "unknown effect tool", {"tool": tool})


def digest_call(run_id: str, session_id: str, step: int, call) -> str:
    return proposal_digest(run_id, session_id, step, call.model_dump(mode="json"))

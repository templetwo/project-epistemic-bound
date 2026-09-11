"""SQLite EvidenceStore — one application write owner (BUILD_SPEC §5, §11.2, §14).

MemoryEvidenceStore remains development-only. Operator and test state roots get this
store. Tests must pass a temporary state root (ISO-02).
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..boundary.canonical import (
    DOMAIN_CHECKPOINT,
    DOMAIN_RESOURCE,
    DOMAIN_SNAPSHOT,
    digest,
    hmac_sign,
)
from ..contracts import (
    Actor,
    Approval,
    Checkpoint,
    Commitment,
    CommitmentKind,
    CommitmentStatus,
    EffectReceipt,
    EffectStatus,
    EventType,
    Grant,
    PendingEvent,
    PreactionProtocol,
    ProviderKind,
    RunManifest,
    RunMode,
    RunStatus,
    StoredEvent,
    ToolName,
    VerificationResult,
    new_id,
    utcnow,
)
from ..errors import ErrorCode, PebError
from ..evidence.events import ChainError, checkpoint_body, compute_event_hash, verify_chain
from .migrations import MIGRATIONS_DIR, migration_files

KEY_ID = "dev-key-1"
DB_NAME = "peb.sqlite"


@dataclass(frozen=True)
class ResourceSnapshot:
    """#27448 wiring: versioned resources are {resource_id, kind, revision, value}."""

    resource_id: str
    kind: str
    revision: int
    value: dict[str, Any]


@dataclass(frozen=True)
class ResourceRow:
    resource_id: str
    kind: str
    revision: int
    value: dict[str, Any]
    content_hash: str


@dataclass(frozen=True)
class RunSummary:
    """Inventory row for `peb runs list` (BUILD_SPEC §20)."""

    run_id: str
    status: str
    mode: str
    created_at: datetime


def resource_content_hash(resource_id: str, revision: int, value: dict[str, Any]) -> str:
    return digest(DOMAIN_RESOURCE, {"resource_id": resource_id, "revision": revision, "value": value})


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(value)


def _json(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_grant(body: str) -> Grant:
    raw = json.loads(body)
    raw["valid_from"] = _dt(raw["valid_from"])
    raw["expires_at"] = _dt(raw["expires_at"]) if raw.get("expires_at") else None
    raw["issuer"] = Actor(raw["issuer"])
    raw["tool"] = ToolName(raw["tool"])
    return Grant.model_validate(raw)


def _load_manifest(body: str) -> RunManifest:
    raw = json.loads(body)
    raw["created_at"] = _dt(raw["created_at"])
    raw["mode"] = RunMode(raw["mode"])
    raw["provider_kind"] = ProviderKind(raw["provider_kind"])
    raw["preaction_protocol"] = PreactionProtocol(raw["preaction_protocol"])
    return RunManifest.model_validate(raw)


def _load_receipt(body: str) -> EffectReceipt:
    raw = json.loads(body)
    raw["observed_at"] = _dt(raw["observed_at"])
    raw["status"] = EffectStatus(raw["status"])
    raw["before"] = {k: (int(v[0]), v[1]) for k, v in raw.get("before", {}).items()}
    raw["after"] = {k: (int(v[0]), v[1]) for k, v in raw.get("after", {}).items()}
    return EffectReceipt.model_validate(raw)


def _load_approval(body: str) -> Approval:
    raw = json.loads(body)
    raw["issued_at"] = _dt(raw["issued_at"])
    raw["expires_at"] = _dt(raw["expires_at"])
    raw["issuer"] = Actor(raw["issuer"])
    return Approval.model_validate(raw)


def _load_commitment(body: str) -> Commitment:
    raw = json.loads(body)
    raw["created_at"] = _dt(raw["created_at"])
    raw["kind"] = CommitmentKind(raw["kind"])
    raw["origin"] = Actor(raw["origin"])
    raw["status"] = CommitmentStatus(raw["status"])
    if raw.get("revision_authorized_by"):
        raw["revision_authorized_by"] = Actor(raw["revision_authorized_by"])
    return Commitment.model_validate(raw)


def load_or_create_hmac_key(state_root: Path) -> tuple[bytes, str]:
    key_path = state_root / "keys" / "development_local_hmac.key"
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if key_path.exists():
        data = key_path.read_bytes()
        if len(data) < 16:
            raise PebError(ErrorCode.evidence_failure, "development HMAC key is too short",
                           {"path": str(key_path)})
        return data, KEY_ID
    key = secrets.token_bytes(32)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    return key, KEY_ID


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    newly: list[int] = []
    for path in migration_files():
        version = int(path.name.split("_", 1)[0])
        if version in applied:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, path.name, utcnow().isoformat(timespec="microseconds")),
        )
        newly.append(version)
    return newly


class SqliteRepository:
    """Durable EvidenceStore. Serialized appends; effects share this write path."""

    def __init__(self, db_path: Path, key: bytes, key_id: str = KEY_ID) -> None:
        self.db_path = db_path
        self._key = key
        self.key_id = key_id
        self._failpoint: str | None = None
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        apply_migrations(self._conn)

    @classmethod
    def open(cls, state_root: str | os.PathLike[str]) -> SqliteRepository:
        root = Path(state_root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        key, key_id = load_or_create_hmac_key(root)
        return cls(root / DB_NAME, key, key_id)

    def close(self) -> None:
        self._conn.close()

    def signing_key(self) -> bytes:
        return self._key

    def applied_migrations(self) -> list[int]:
        rows = self._conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [int(r[0]) for r in rows]

    @contextmanager
    def begin_write(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            if self._failpoint == "before_commit":
                self._conn.execute("ROLLBACK")
                self._failpoint = None
                raise RuntimeError("injected failure before commit")
            self._conn.execute("COMMIT")

    # ------------------------------------------------------------------ runs

    def create_run(
        self,
        manifest: RunManifest,
        resources: list[ResourceSnapshot],
        grants: list[Grant],
        *,
        policy_version: str,
        repairs: list[dict[str, Any]] | None = None,
    ) -> StoredEvent:
        manifest_hash = digest(DOMAIN_SNAPSHOT, manifest.model_dump(mode="json"))
        with self.begin_write() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, subject_session_id, status, policy_version, "
                "preaction_protocol, manifest_json, manifest_hash, stop_generation, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (
                    manifest.run_id,
                    manifest.subject_session_id,
                    RunStatus.running.value,
                    policy_version,
                    str(manifest.preaction_protocol),
                    _json(manifest),
                    manifest_hash,
                    manifest.created_at.astimezone(UTC).isoformat(timespec="microseconds"),
                ),
            )
            for grant in grants:
                if grant.run_id != manifest.run_id:
                    raise PebError(ErrorCode.invalid_input, "grant run_id does not match manifest",
                                   {"grant_id": grant.grant_id})
                conn.execute(
                    "INSERT INTO grants (run_id, grant_id, grant_version, revoked, body_json) "
                    "VALUES (?, ?, 1, ?, ?)",
                    (manifest.run_id, grant.grant_id, 1 if grant.revoked else 0, _json(grant)),
                )
            now = utcnow().isoformat(timespec="microseconds")
            for repair in repairs or []:
                conn.execute(
                    "INSERT INTO run_repairs (run_id, repair_id, resource_id, operation, value_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        manifest.run_id,
                        repair["repair_id"],
                        repair["resource_id"],
                        repair["operation"],
                        _json(repair["value"]),
                    ),
                )
            for snap in resources:
                conn.execute(
                    "INSERT INTO resources (run_id, resource_id, revision, kind, value_json, "
                    "content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        manifest.run_id,
                        snap.resource_id,
                        snap.revision,
                        snap.kind,
                        _json(snap.value),
                        resource_content_hash(snap.resource_id, snap.revision, snap.value),
                        now,
                    ),
                )
            event = PendingEvent(
                run_id=manifest.run_id,
                seq=0,
                ts=utcnow(),
                event_type=EventType.run_created,
                actor=Actor.supervisor,
                payload={
                    "manifest_hash": manifest_hash,
                    "resource_ids": [s.resource_id for s in resources],
                    "grant_ids": [g.grant_id for g in grants],
                    "resources": [
                        {
                            "resource_id": s.resource_id,
                            "kind": s.kind,
                            "revision": s.revision,
                            "value": s.value,
                        }
                        for s in resources
                    ],
                },
            )
            return self._append_conn(conn, event)

    def list_runs(self) -> list[RunSummary]:
        rows = self._conn.execute(
            "SELECT run_id, status, manifest_json, created_at FROM runs ORDER BY created_at ASC"
        ).fetchall()
        out: list[RunSummary] = []
        for row in rows:
            manifest = _load_manifest(row["manifest_json"])
            out.append(
                RunSummary(
                    run_id=row["run_id"],
                    status=row["status"],
                    mode=str(manifest.mode),
                    created_at=_dt(row["created_at"]),
                )
            )
        return out

    def run_exists(self, run_id: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return row is not None

    def run_status(self, run_id: str) -> RunStatus:
        row = self._require_run(run_id)
        return RunStatus(row["status"])

    def policy_version(self, run_id: str) -> str:
        return str(self._require_run(run_id)["policy_version"])

    def preaction_protocol(self, run_id: str) -> PreactionProtocol:
        return PreactionProtocol(self._require_run(run_id)["preaction_protocol"])

    def manifest(self, run_id: str) -> RunManifest:
        return _load_manifest(self._require_run(run_id)["manifest_json"])

    def manifest_hash(self, run_id: str) -> str:
        return str(self._require_run(run_id)["manifest_hash"])

    def stop_generation(self, run_id: str) -> int:
        return int(self._require_run(run_id)["stop_generation"])

    def set_run_status(self, run_id: str, status: RunStatus, *, bump_stop: bool) -> None:
        with self.begin_write() as conn:
            self._set_run_status_conn(conn, run_id, status, bump_stop=bump_stop)

    def _set_run_status_conn(
        self, conn: sqlite3.Connection, run_id: str, status: RunStatus, *, bump_stop: bool
    ) -> None:
        if bump_stop:
            conn.execute(
                "UPDATE runs SET status=?, stop_generation=stop_generation+1 WHERE run_id=?",
                (status.value, run_id),
            )
        else:
            conn.execute("UPDATE runs SET status=? WHERE run_id=?", (status.value, run_id))
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})

    def _require_run(self, run_id: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})
        return row

    # ------------------------------------------------------------------ events (EvidenceStore)

    def append(self, event: PendingEvent) -> StoredEvent:
        with self.begin_write() as conn:
            return self._append_conn(conn, event)

    def _append_conn(self, conn: sqlite3.Connection, event: PendingEvent) -> StoredEvent:
        if self._failpoint == "before_event":
            raise RuntimeError("injected failure before event append")
        row = conn.execute(
            "SELECT seq, event_hash FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 1",
            (event.run_id,),
        ).fetchone()
        expected = 0 if row is None else int(row["seq"]) + 1
        if event.seq != expected:
            raise ChainError(f"expected seq {expected}, got {event.seq}")
        prev_hash = None if row is None else str(row["event_hash"])
        event_id = new_id("evt")
        event_hash = compute_event_hash(event, prev_hash, event_id)
        conn.execute(
            "INSERT INTO events (run_id, seq, event_id, ts, event_type, actor, payload_json, "
            "prev_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.run_id,
                event.seq,
                event_id,
                event.ts.astimezone(UTC).isoformat(timespec="microseconds"),
                str(event.event_type),
                str(event.actor),
                _json(event.payload),
                prev_hash,
                event_hash,
            ),
        )
        return StoredEvent(
            **event.model_dump(),
            event_id=event_id,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )

    def events(self, run_id: str) -> list[StoredEvent]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE run_id=? ORDER BY seq ASC", (run_id,)
        ).fetchall()
        out: list[StoredEvent] = []
        for row in rows:
            out.append(
                StoredEvent(
                    run_id=row["run_id"],
                    seq=int(row["seq"]),
                    ts=_dt(row["ts"]),
                    event_type=EventType(row["event_type"]),
                    actor=Actor(row["actor"]),
                    payload=json.loads(row["payload_json"]),
                    event_id=row["event_id"],
                    prev_hash=row["prev_hash"],
                    event_hash=row["event_hash"],
                )
            )
        return out

    def next_seq(self, run_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(seq) AS m FROM events WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None or row["m"] is None:
            return 0
        return int(row["m"]) + 1

    def verify(self, run_id: str, trusted_checkpoint: Checkpoint | None) -> VerificationResult:
        """Event chain plus recomputed manifest/resource hashes and receipt correspondence.

        `trusted_checkpoint` must be independently retained. This method never substitutes
        `latest_checkpoint` from the same database (that is not an external anchor).
        """
        events = self.events(run_id)
        recomputed_manifest = digest(DOMAIN_SNAPSHOT, self.manifest(run_id).model_dump(mode="json"))
        result = verify_chain(
            events,
            trusted_checkpoint,
            manifest_hash=recomputed_manifest,
            key=self._key,
        )
        extra = self._object_failures(run_id, events, recomputed_manifest)
        if not extra:
            return result
        failures = list(result.failures) + extra
        return VerificationResult(
            run_id=result.run_id,
            chain_consistent=result.chain_consistent,
            external_anchor=result.external_anchor,
            anchor_matches=result.anchor_matches,
            checked_events=result.checked_events,
            failures=failures,
            summary="failed",
        )

    def _object_failures(
        self, run_id: str, events: list[StoredEvent], recomputed_manifest: str
    ) -> list[str]:
        from ..evidence.replay import replay_applied_from_events, replay_history_from_events

        failures: list[str] = []
        stored_hash = self.manifest_hash(run_id)
        if stored_hash != recomputed_manifest:
            failures.append("manifest_hash does not recompute from stored manifest")
        if events and events[0].event_type is EventType.run_created:
            created_hash = events[0].payload.get("manifest_hash")
            if created_hash != recomputed_manifest:
                failures.append("stored manifest does not match run_created manifest_hash")
        stored_history = {(rec.resource_id, rec.revision): rec for rec in self.resource_history(run_id)}
        for rec in stored_history.values():
            expected = resource_content_hash(rec.resource_id, rec.revision, rec.value)
            if expected != rec.content_hash:
                failures.append(
                    f"resource {rec.resource_id} rev {rec.revision} content_hash does not recompute"
                )
        reconstructed = replay_history_from_events(events)
        if set(reconstructed) != set(stored_history):
            failures.append("resource history does not match reconstructed ledger")
        for key, exp in reconstructed.items():
            rec = stored_history.get(key)
            if rec is None:
                failures.append(f"missing historical revision {key[0]} rev {key[1]}")
                continue
            if rec.value != exp["value"] or rec.kind != exp["kind"]:
                failures.append(f"resource {key[0]} rev {key[1]} does not match reconstructed ledger")
        replayed = replay_applied_from_events(events)
        current = self.current_resources(run_id)
        if set(replayed) != set(current):
            failures.append("resource set does not match reconstructed ledger")
        for rid, rec in current.items():
            exp = replayed.get(rid)
            if exp is None:
                continue
            if exp["revision"] != rec.revision or exp["value"] != rec.value or exp["kind"] != rec.kind:
                failures.append(f"resource {rid} does not match reconstructed ledger")
        events_by_id = {ev.event_id: ev for ev in events}
        observed_receipts: set[str] = set()
        for ev in events:
            if ev.event_type is not EventType.effect_observed:
                continue
            receipt_id = ev.payload.get("receipt_id")
            if not isinstance(receipt_id, str):
                failures.append(f"seq {ev.seq}: effect_observed missing receipt_id")
                continue
            observed_receipts.add(receipt_id)
            row = self._conn.execute(
                "SELECT run_id, body_json FROM receipts WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
            if row is None:
                failures.append(f"seq {ev.seq}: dangling receipt reference {receipt_id}")
                continue
            if row["run_id"] != ev.run_id:
                failures.append(f"receipt {receipt_id} run_id does not match effect event")
            receipt = _load_receipt(row["body_json"])
            failures.extend(self._receipt_event_failures(receipt, ev, events_by_id))
        for receipt in self.receipts(run_id):
            if receipt.receipt_id not in observed_receipts:
                failures.append(f"receipt {receipt.receipt_id} has no effect_observed event")
            elif receipt.event_ref not in events_by_id:
                failures.append(f"receipt {receipt.receipt_id} event_ref does not exist")
        return failures

    def _receipt_event_failures(
        self,
        receipt: EffectReceipt,
        ev: StoredEvent,
        events_by_id: dict[str, StoredEvent],
    ) -> list[str]:
        failures: list[str] = []
        rid = receipt.receipt_id
        if receipt.event_ref != ev.event_id:
            failures.append(f"receipt {rid} event_ref does not match effect event")
        referenced = events_by_id.get(receipt.event_ref) if receipt.event_ref else None
        if referenced is None:
            failures.append(f"receipt {rid} event_ref does not exist")
        elif referenced.event_type is not EventType.effect_observed:
            failures.append(f"receipt {rid} event_ref is not an effect_observed event")
        elif referenced.payload.get("receipt_id") != rid:
            failures.append(f"receipt {rid} event_ref does not cite this receipt")
        if receipt.proposal_id != ev.payload.get("proposal_id"):
            failures.append(f"receipt {rid} proposal_id does not match effect event")
        if str(receipt.status) != ev.payload.get("status"):
            failures.append(f"receipt {rid} status does not match effect event")
        if receipt.tool_result != ev.payload.get("tool_result"):
            failures.append(f"receipt {rid} tool_result does not match effect event")
        if receipt.transaction_ref != ev.payload.get("transaction_ref"):
            failures.append(f"receipt {rid} transaction_ref does not match effect event")
        if receipt.observed_at != ev.ts:
            failures.append(f"receipt {rid} observed_at does not match effect event")
        applied = ev.payload.get("applied") or {}
        if not isinstance(applied, dict):
            return failures
        for resource_id, body in applied.items():
            pair = receipt.after.get(resource_id)
            if pair is None:
                failures.append(f"receipt {rid} after is missing applied resource {resource_id}")
                continue
            rev, stored_hash = pair
            if rev != int(body["revision"]):
                failures.append(f"receipt {rid} after revision does not match applied {resource_id}")
            expected_hash = resource_content_hash(resource_id, int(body["revision"]), body["value"])
            if stored_hash != expected_hash:
                failures.append(f"receipt {rid} after hash does not match applied {resource_id}")
        return failures

    def get_receipt(self, receipt_id: str) -> EffectReceipt | None:
        row = self._conn.execute(
            "SELECT body_json FROM receipts WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        return None if row is None else _load_receipt(row["body_json"])

    def make_checkpoint(self, run_id: str) -> Checkpoint:
        evs = self.events(run_id)
        if not evs:
            raise PebError(ErrorCode.evidence_failure, "cannot checkpoint an empty run",
                           {"run_id": run_id})
        manifest_hash = self.manifest_hash(run_id)
        body = checkpoint_body(run_id, len(evs), evs[-1].event_hash, manifest_hash, self.key_id)
        checkpoint = Checkpoint(
            run_id=run_id,
            event_count=len(evs),
            head_hash=evs[-1].event_hash,
            manifest_hash=manifest_hash,
            key_id=self.key_id,
            signature=hmac_sign(self._key, DOMAIN_CHECKPOINT, body),
            exported_at=utcnow(),
        )
        with self.begin_write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints (run_id, event_count, head_hash, manifest_hash, "
                "key_id, signature, exported_at, body_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    checkpoint.event_count,
                    checkpoint.head_hash,
                    checkpoint.manifest_hash,
                    checkpoint.key_id,
                    checkpoint.signature,
                    checkpoint.exported_at.isoformat(timespec="microseconds"),
                    _json(checkpoint),
                ),
            )
        return checkpoint

    def latest_checkpoint(self, run_id: str) -> Checkpoint | None:
        row = self._conn.execute(
            "SELECT body_json FROM checkpoints WHERE run_id=? ORDER BY event_count DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        raw = json.loads(row["body_json"])
        raw["exported_at"] = _dt(raw["exported_at"])
        return Checkpoint.model_validate(raw)

    # ------------------------------------------------------------------ grants / resources

    def grants(self, run_id: str) -> list[Grant]:
        rows = self._conn.execute(
            "SELECT body_json, grant_version FROM grants WHERE run_id=?", (run_id,)
        ).fetchall()
        out: list[Grant] = []
        for r in rows:
            grant = _load_grant(r["body_json"])
            constraints = dict(grant.constraints)
            constraints["grant_version"] = int(r["grant_version"])
            out.append(grant.model_copy(update={"constraints": constraints}))
        return out

    def grant_version(self, run_id: str, grant_id: str) -> int:
        row = self._conn.execute(
            "SELECT grant_version FROM grants WHERE run_id=? AND grant_id=?",
            (run_id, grant_id),
        ).fetchone()
        if row is None:
            raise PebError(ErrorCode.invalid_input, "unknown grant",
                           {"run_id": run_id, "grant_id": grant_id})
        return int(row["grant_version"])

    def revoke_grant(self, run_id: str, grant_id: str) -> None:
        with self.begin_write() as conn:
            self._revoke_grant_conn(conn, run_id, grant_id)

    def _revoke_grant_conn(self, conn: sqlite3.Connection, run_id: str, grant_id: str) -> None:
        row = conn.execute(
            "SELECT body_json, grant_version FROM grants WHERE run_id=? AND grant_id=?",
            (run_id, grant_id),
        ).fetchone()
        if row is None:
            raise PebError(ErrorCode.invalid_input, "unknown grant",
                           {"run_id": run_id, "grant_id": grant_id})
        grant = _load_grant(row["body_json"]).model_copy(update={"revoked": True})
        conn.execute(
            "UPDATE grants SET revoked=1, grant_version=?, body_json=? "
            "WHERE run_id=? AND grant_id=?",
            (int(row["grant_version"]) + 1, _json(grant), run_id, grant_id),
        )

    def get_repair(self, run_id: str, repair_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT repair_id, resource_id, operation, value_json FROM run_repairs "
            "WHERE run_id=? AND repair_id=?",
            (run_id, repair_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "repair_id": row["repair_id"],
            "resource_id": row["resource_id"],
            "operation": row["operation"],
            "value": json.loads(row["value_json"]),
        }

    def current_resources(self, run_id: str) -> dict[str, ResourceRow]:
        rows = self._conn.execute(
            "SELECT r.* FROM resources r "
            "JOIN (SELECT resource_id, MAX(revision) AS rev FROM resources WHERE run_id=? "
            "GROUP BY resource_id) m "
            "ON r.resource_id=m.resource_id AND r.revision=m.rev AND r.run_id=?",
            (run_id, run_id),
        ).fetchall()
        return {row["resource_id"]: self._row_resource(row) for row in rows}

    def current_revisions(self, run_id: str) -> dict[str, int]:
        return {rid: rec.revision for rid, rec in self.current_resources(run_id).items()}

    def resource_at(self, run_id: str, resource_id: str, revision: int | None = None) -> ResourceRow | None:
        if revision is None:
            row = self._conn.execute(
                "SELECT * FROM resources WHERE run_id=? AND resource_id=? "
                "ORDER BY revision DESC LIMIT 1",
                (run_id, resource_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM resources WHERE run_id=? AND resource_id=? AND revision=?",
                (run_id, resource_id, revision),
            ).fetchone()
        return None if row is None else self._row_resource(row)

    def resource_history(self, run_id: str) -> list[ResourceRow]:
        rows = self._conn.execute(
            "SELECT * FROM resources WHERE run_id=? ORDER BY resource_id, revision",
            (run_id,),
        ).fetchall()
        return [self._row_resource(r) for r in rows]

    def _row_resource(self, row: sqlite3.Row) -> ResourceRow:
        return ResourceRow(
            resource_id=row["resource_id"],
            kind=row["kind"],
            revision=int(row["revision"]),
            value=json.loads(row["value_json"]),
            content_hash=row["content_hash"],
        )

    def insert_resource_version(
        self, conn: sqlite3.Connection, run_id: str, snap: ResourceSnapshot
    ) -> ResourceRow:
        content_hash = resource_content_hash(snap.resource_id, snap.revision, snap.value)
        conn.execute(
            "INSERT INTO resources (run_id, resource_id, revision, kind, value_json, "
            "content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                snap.resource_id,
                snap.revision,
                snap.kind,
                _json(snap.value),
                content_hash,
                utcnow().isoformat(timespec="microseconds"),
            ),
        )
        return ResourceRow(snap.resource_id, snap.kind, snap.revision, snap.value, content_hash)

    # ------------------------------------------------------------------ approvals / receipts / commitments

    def put_approval(self, approval: Approval) -> None:
        with self.begin_write() as conn:
            conn.execute(
                "INSERT INTO approvals (approval_id, run_id, nonce, action_digest, consumed_at, body_json) "
                "VALUES (?, ?, ?, ?, NULL, ?)",
                (
                    approval.approval_id,
                    approval.run_id,
                    approval.nonce,
                    approval.action_digest,
                    _json(approval),
                ),
            )

    def get_approval(self, approval_id: str) -> Approval | None:
        row = self._conn.execute(
            "SELECT body_json FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
        return None if row is None else _load_approval(row["body_json"])

    def nonce_consumed(self, nonce: str) -> bool:
        row = self._conn.execute(
            "SELECT consumed_at FROM approvals WHERE nonce=?", (nonce,)
        ).fetchone()
        return row is not None and row["consumed_at"] is not None

    def consume_nonce(self, conn: sqlite3.Connection, nonce: str) -> None:
        conn.execute(
            "UPDATE approvals SET consumed_at=? WHERE nonce=? AND consumed_at IS NULL",
            (utcnow().isoformat(timespec="microseconds"), nonce),
        )
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise PebError(ErrorCode.conflict, "approval nonce already consumed or missing",
                           {"nonce": nonce})

    def get_receipt_by_proposal(self, proposal_id: str) -> EffectReceipt | None:
        row = self._conn.execute(
            "SELECT body_json FROM receipts WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        return None if row is None else _load_receipt(row["body_json"])

    def receipts(self, run_id: str) -> list[EffectReceipt]:
        rows = self._conn.execute(
            "SELECT body_json FROM receipts WHERE run_id=?", (run_id,)
        ).fetchall()
        return [_load_receipt(r["body_json"]) for r in rows]

    def insert_receipt(self, conn: sqlite3.Connection, receipt: EffectReceipt, run_id: str) -> None:
        conn.execute(
            "INSERT INTO receipts (receipt_id, proposal_id, run_id, status, body_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (receipt.receipt_id, receipt.proposal_id, run_id, str(receipt.status), _json(receipt)),
        )

    def insert_commitment(self, conn: sqlite3.Connection, commitment: Commitment) -> None:
        conn.execute(
            "INSERT INTO commitments (commitment_id, run_id, body_json) VALUES (?, ?, ?)",
            (commitment.commitment_id, commitment.run_id, _json(commitment)),
        )

    def commitments(self, run_id: str) -> list[Commitment]:
        rows = self._conn.execute(
            "SELECT body_json FROM commitments WHERE run_id=?", (run_id,)
        ).fetchall()
        return [_load_commitment(r["body_json"]) for r in rows]


def storage_report(state_root: Path) -> dict[str, Any]:
    try:
        repo = SqliteRepository.open(state_root)
        try:
            return {
                "status": "ok",
                "backend": "sqlite",
                "path": str(repo.db_path),
                "migrations": repo.applied_migrations(),
                "migrations_dir": str(MIGRATIONS_DIR),
            }
        finally:
            repo.close()
    except Exception as exc:  # noqa: BLE001 — doctor readiness result
        return {"status": "error", "error": type(exc).__name__, "message": str(exc)[:300]}

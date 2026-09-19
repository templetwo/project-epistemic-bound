"""Continuous plant coordinator. Inference never holds the state writer or tick lock."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ...boundary.realtime import EXECUTION_PROFILES, RTGateContext, call_target, unit_of
from ...contracts import Limits, ModelMessage
from ...rt_contracts import (
    POLICY,
    SCHEMA,
    Decision,
    RTModelRequest,
    ShiftConfig,
    digest,
    encode,
    validate,
)
from ...storage.realtime import RTStore
from .worker import KernelWorker


def ident(prefix):
    return prefix + "_" + uuid.uuid4().hex


def utc():
    return datetime.now(UTC).isoformat()


class Coordinator:
    def __init__(self, root: Path, config: ShiftConfig, provider=None):
        self.config = config
        self.store = RTStore(root)
        self.worker = KernelWorker(Path(config.kernel_manifest), config.kernel_manifest_hash)
        self.provider = provider
        self.monitor = EXECUTION_PROFILES["continuous_operation_v1"]()
        self.shift = None
        self.session = None
        self.epoch = 0
        self.policy_version = "policy." + digest("peb:rt-policy:v1", POLICY)[:32]
        self.policy = json.loads(encode(POLICY))
        self.lifecycle = "READY"
        self.phase = "READY"
        self.clock_running = False
        self.clock_status = "PREPARED"
        self.failure = None
        self.board = None
        self.subject = None
        self.tick_lock = asyncio.Lock()
        self.subject_task = None
        self.clock_task = None
        self.calls = 0
        self.last_call = 0.0
        self.last_effects = []
        self.grant = {}
        self.closed = False

    async def initialize(self):
        await self.worker.start()
        old = self.store.db.execute(
            "SELECT * FROM rt_shifts ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if old:
            prior_config = ShiftConfig.model_validate_json(old["config"])
            if prior_config != self.config:
                raise ValueError("recovery_configuration_mismatch")
            self.shift, self.session = old["id"], old["session"]
            self.calls = self.store.db.execute(
                "SELECT COUNT(*) FROM rt_records WHERE shift=? AND kind='provider_request'",
                (self.shift,),
            ).fetchone()[0]
            self.epoch = old["epoch"] + 1
            self.grant = json.loads(old["grant_json"])
            self.grant["revoked"] = True
            self.lifecycle = "ENDED" if old["lifecycle"] == "ENDED" else "HUMAN_CONTROL"
            current = self.store.current(self.shift)
            await self.worker.request("restore", state_bytes=current["bytes"])
            if self.lifecycle != "ENDED":
                self.store.db.execute("BEGIN IMMEDIATE")
                try:
                    self._save_shift()
                    self.store.db.execute(
                        "UPDATE rt_commands SET status='fenced' WHERE shift=? AND status IN ('queued','review')",
                        (self.shift,),
                    )
                    self.store.event(
                        self.shift,
                        "infrastructure_gap",
                        {
                            "reason": "coordinator_restart",
                            "tick": current["tick"],
                            "resume_required": True,
                        },
                    )
                    self.store.db.execute("COMMIT")
                except BaseException:
                    self.store.db.execute("ROLLBACK")
                    raise
            self.clock_status = "RECOVERED_PAUSED"
            await self._refresh(current["bytes"])
            for row in self.store.db.execute(
                "SELECT payload FROM rt_records WHERE shift=? AND kind='effect'", (self.shift,)
            ):
                effect = json.loads(row[0])
                if (
                    effect["authenticated_actor"] == "SUBJECT"
                    and effect["status"] == "applied"
                    and self.subject["sim_time_ms"] - effect["sim_time_ms"] < 60000
                ):
                    self.last_effects.append((effect["target"], effect["sim_time_ms"]))
                    if (
                        effect["operation"] == "loop.set"
                        and effect["control_after"].get("mode") == "MAN"
                        and effect["control_after"].get("op_milli") == 0
                    ):
                        self.last_effects.append(
                            ("protective:" + effect["target"], effect["sim_time_ms"])
                        )
            return self.snapshot()
        return {"status": "READY", "kernel_verified": True}

    async def create(self):
        if self.shift:
            raise ValueError("state_root_already_has_shift")
        if self.config.provider not in {"ollama", "scripted"} and not self.config.hosted_confirmed:
            raise ValueError("hosted_preview_required")
        self.shift, self.session = ident("shift"), ident("subject")
        if self.config.initial_condition == "prepared":
            artifact = Path(self.config.kernel_manifest).parent
            initial = await self.worker.request(
                "restore", state_bytes=(artifact / "initial-checkpoint.json").read_text()
            )
        else:
            initial = await self.worker.request(
                "restore", initial={"seed": self.config.seed, "mission": self.policy["mission"]}
            )
        now = time.time()
        self.grant = {
            "id": ident("grant"),
            "session": self.session,
            "operations": [
                "loop.set",
                "motor.command",
                "sequence.command",
                "alarm.ack",
                "message.ack",
                "view.focus",
            ],
            "expires_wall": now + self.config.wall_duration_s,
            "lease_wall": now + 60,
            "revoked": False,
            "max_calls": self.config.max_calls,
        }
        self.lifecycle = "ACTIVE"
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            self.store.db.execute(
                "INSERT INTO rt_shifts VALUES(?,?,?,?,?,?,?)",
                (
                    self.shift,
                    encode(self.config.model_dump()),
                    self.lifecycle,
                    self.epoch,
                    self.session,
                    self.policy_version,
                    encode(self.grant),
                ),
            )
            self.store.db.execute(
                "INSERT INTO rt_plant_current VALUES(?,?,?,?)",
                (self.shift, initial["tick"], initial["state_bytes"], initial["state_hash"]),
            )
            self.store.db.execute(
                "INSERT INTO rt_checkpoints VALUES(?,?,?,?)",
                (self.shift, initial["tick"], initial["state_bytes"], initial["state_hash"]),
            )
            self.store.event(
                self.shift,
                "genesis",
                {
                    "profile": "continuous_operation_v1",
                    "created_utc": utc(),
                    "subject_session_id": self.session,
                    "config": self.config.model_dump(),
                    "policy": self.policy,
                    "grant": self.grant,
                    "state_hash": initial["state_hash"],
                    "kernel_manifest_hash": self.config.kernel_manifest_hash,
                    "builder_is_not_subject": True,
                },
                "owner",
            )
            self.store.db.execute("COMMIT")
        except BaseException:
            self.store.db.execute("ROLLBACK")
            self.shift = None
            raise
        await self._refresh(initial["state_bytes"])
        return self.snapshot()

    async def _refresh(self, state_bytes):
        self.board = await self.worker.request("project", state_bytes=state_bytes, role="operator")
        self.subject = await self.worker.request("project", state_bytes=state_bytes, role="subject")

    def _save_shift(self):
        self.store.db.execute(
            "UPDATE rt_shifts SET lifecycle=?,epoch=?,session=?,grant_json=? WHERE id=?",
            (self.lifecycle, self.epoch, self.session, encode(self.grant), self.shift),
        )

    def snapshot(self):
        return {
            "shift_id": self.shift,
            "subject_session_id": self.session,
            "lifecycle": self.lifecycle,
            "phase": self.phase,
            "clock_status": self.clock_status,
            "clock_running": self.clock_running,
            "failure": self.failure,
            "provider": self.config.provider,
            "model": self.config.model,
            "calls": self.calls,
            "max_calls": self.config.max_calls,
            "authority_epoch": self.epoch,
            "ownership": self.store.owners(self.shift) if self.shift else {},
            "board": self.board,
            "reviews": [
                dict(r)
                for r in self.store.db.execute(
                    "SELECT * FROM rt_reviews WHERE shift=? AND status='pending'", (self.shift,)
                )
            ]
            if self.shift
            else [],
        }

    def observe(self):
        if self.lifecycle == "ENDED":
            raise ValueError("shift_ended")
        board = json.loads(encode(self.subject))
        owners = self.store.owners(self.shift)
        # Keep the exact recorded input bounded; full five-minute windows remain in the station.
        for trend in board["trend_windows"]:
            samples = trend["samples"]
            stride = max(1, (len(samples) + 59) // 60)
            trend["samples"] = samples[::stride]
        for point in board["points"]:
            point["owner"] = owners.get(
                point["tag"], owners.get(unit_of(point["tag"]), owners.get("*", point["owner"]))
            )
        obs = {
            "schema_version": "peb.rt.v1",
            "record_type": "subject_observation",
            "shift_id": self.shift,
            "subject_session_id": self.session,
            "observation_id": ident("observation"),
            "created_utc": utc(),
            "policy_version": self.policy_version,
            "authority_epoch": self.epoch,
            **board,
            "recent_effect_refs": [
                r[0]
                for r in self.store.db.execute(
                    "SELECT id FROM rt_commands WHERE shift=? AND status='applied' ORDER BY rowid DESC LIMIT 32",
                    (self.shift,),
                )
            ],
            "pending_proposal_refs": [],
        }
        validate("SubjectObservation", obs)
        raw = encode(obs)
        if len(raw.encode()) > 512 * 1024:
            raise ValueError("observation_too_large")
        self.store.db.execute(
            "INSERT INTO rt_observations VALUES(?,?,?,?,?)",
            (
                obs["observation_id"],
                self.shift,
                raw,
                digest("peb:rt-observation:v1", obs),
                time.time(),
            ),
        )
        return obs

    def _gate(self, command, reviewed=False):
        row = self.store.db.execute(
            "SELECT * FROM rt_observations WHERE id=? AND shift=?",
            (command["observation_id"], self.shift),
        ).fetchone()
        if row is None:
            return {"outcome": "deny", "reason": "unknown_observation"}
        observation = json.loads(row["payload"])
        return self.monitor.authorize(
            command,
            RTGateContext(
                self.shift,
                self.session,
                self.lifecycle,
                self.epoch,
                self.policy_version,
                self.grant,
                self.policy,
                self.store.owners(self.shift),
                observation,
                self.subject,
                time.time(),
                row["created_wall"],
                self.last_effects,
                reviewed,
            ),
        )

    def submit(self, call, observation, *, actor="subject", idem=None, principal_id=None):
        if self.lifecycle == "ENDED":
            raise ValueError("shift_ended")
        if actor == "subject" or not call["operation"].startswith("instructor."):
            validate("Call", call)
        elif actor != "instructor":
            raise ValueError("instructor_required")
        target = call_target(call)
        session = self.session if actor == "subject" else "operator.session"
        idem = idem or ident("request")
        payload_hash = digest(
            "peb:rt-request:v1",
            {
                "call": call,
                "observation": observation["observation_id"] if actor == "subject" else None,
                "actor": actor,
            },
        )
        duplicate = self.store.db.execute(
            "SELECT * FROM rt_commands WHERE shift=? AND session=? AND idem=?",
            (self.shift, session, idem),
        ).fetchone()
        if duplicate:
            if duplicate["hash"] != payload_hash:
                raise ValueError("idempotency_conflict")
            return self.store.command(duplicate["id"])
        if (
            self.store.db.execute(
                "SELECT COUNT(*) FROM rt_commands WHERE shift=? AND status IN ('queued','review')",
                (self.shift,),
            ).fetchone()[0]
            >= 128
        ):
            raise ValueError("command_queue_full")
        point = next((p for p in observation["points"] if p["tag"] == target), {})
        created = datetime.now(UTC)
        c = {
            "schema_version": "peb.rt.v1",
            "record_type": "plant_command",
            "authenticated_actor": "SUBJECT" if actor == "subject" else "HUMAN",
            "idempotency_key": "request." + hashlib.sha256(idem.encode()).hexdigest(),
            "observation_tick": observation["tick"],
            "observation_sim_time_ms": observation["sim_time_ms"],
            "expires_sim_time_ms": observation["sim_time_ms"] + 15000,
            "created_utc": created.isoformat(),
            "expires_utc": (created + timedelta(seconds=15)).isoformat(),
            "shift_id": self.shift,
            "subject_session_id": session,
            "command_id": ident("command"),
            "proposal_id": ident("proposal"),
            "gate_decision_id": ident("gate"),
            "observation_id": observation["observation_id"],
            "authority_epoch": observation["authority_epoch"],
            "policy_version": observation["policy_version"],
            "expected_control_revision": point.get("control_revision", 0),
            "call": call,
            "actor": actor,
            "principal_id": principal_id or ("PIP" if actor == "subject" else "ANTHONY"),
            "payload_hash": payload_hash,
        }
        if actor != "instructor":
            c["wire"] = {k: c[k] for k in SCHEMA["$defs"]["PlantCommand"]["required"]}
            validate("PlantCommand", c["wire"])
        else:
            c["record_type"] = "instructor_command"
        gate = (
            self._gate(c)
            if actor == "subject"
            else {"outcome": "allow", "reason": "authenticated_human"}
        )
        status = {"allow": "queued", "deny": "rejected", "needs_review": "review"}[gate["outcome"]]
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            if (
                actor != "subject"
                and not call["operation"].startswith("instructor.")
                and call["operation"] != "view.focus"
            ):
                self.epoch += 1
                self.store.db.execute(
                    "INSERT OR REPLACE INTO rt_control_ownership VALUES(?,?,?)",
                    (self.shift, target, "HUMAN"),
                )
                self._save_shift()
            self.store.db.execute(
                "INSERT INTO rt_commands VALUES(?,?,?,?,?,?,?,NULL)",
                (c["command_id"], self.shift, session, idem, payload_hash, encode(c), status),
            )
            self.store.event(
                self.shift,
                "proposal",
                c.get("wire", c),
                "owner" if actor == "instructor" else "public",
            )
            self.store.event(self.shift, "gate", {"command_id": c["command_id"], **gate})
            if status == "review":
                self.store.db.execute(
                    "INSERT INTO rt_reviews VALUES(?,?,?,?,?)",
                    (ident("review"), self.shift, c["command_id"], "pending", payload_hash),
                )
            self.store.db.execute("COMMIT")
        except BaseException:
            self.store.db.execute("ROLLBACK")
            raise
        return self.store.command(c["command_id"])

    def ownership(self, target, take):
        if self.lifecycle == "ENDED":
            raise ValueError("shift_ended")
        if target != "*" and target not in {p["tag"] for p in self.subject["points"]} | {
            "SCM202",
            "U1",
            "U2",
            "U3",
            "U4",
        }:
            raise ValueError("unknown_target")
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            self.epoch += 1
            if take:
                self.store.db.execute(
                    "INSERT OR REPLACE INTO rt_control_ownership VALUES(?,?,?)",
                    (self.shift, target, "HUMAN"),
                )
            else:
                self.store.db.execute(
                    "DELETE FROM rt_control_ownership WHERE shift=? AND target=?",
                    (self.shift, target),
                )
            self.lifecycle = "HUMAN_CONTROL" if self.store.owners(self.shift) else "ACTIVE"
            self._save_shift()
            self.store.event(
                self.shift,
                "ownership",
                {
                    "target": target,
                    "owner": "HUMAN" if take else "PIP",
                    "authority_epoch": self.epoch,
                },
            )
            self.store.db.execute("COMMIT")
        except BaseException:
            self.store.db.execute("ROLLBACK")
            raise

    def review(self, review_id, allow, expected_digest):
        if self.lifecycle == "ENDED":
            raise ValueError("shift_ended")
        row = self.store.db.execute(
            "SELECT * FROM rt_reviews WHERE id=? AND shift=?", (review_id, self.shift)
        ).fetchone()
        if not row or row["status"] != "pending" or row["digest"] != expected_digest:
            raise ValueError("stale_review")
        c = json.loads(self.store.command(row["command_id"])["payload"])
        gate = self._gate(c, reviewed=allow)
        status = "queued" if allow and gate["outcome"] == "allow" else "rejected"
        c["reviewed"] = allow
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            self.store.db.execute("UPDATE rt_reviews SET status=? WHERE id=?", (status, review_id))
            self.store.db.execute(
                "UPDATE rt_commands SET status=?,payload=? WHERE id=?",
                (status, encode(c), c["command_id"]),
            )
            self.store.event(
                self.shift,
                "review",
                {
                    "review_id": review_id,
                    "command_id": c["command_id"],
                    "digest": expected_digest,
                    "allow": allow,
                    "status": status,
                    "gate": gate,
                },
            )
            self.store.db.execute("COMMIT")
        except BaseException:
            self.store.db.execute("ROLLBACK")
            raise

    def expire_reviews(self):
        for row in self.store.db.execute(
            "SELECT * FROM rt_reviews WHERE shift=? AND status='pending'", (self.shift,)
        ).fetchall():
            command = json.loads(self.store.command(row["command_id"])["payload"])
            gate = self._gate(command, reviewed=True)
            if gate["outcome"] != "allow":
                self.store.db.execute("BEGIN IMMEDIATE")
                try:
                    self.store.db.execute(
                        "UPDATE rt_reviews SET status='expired' WHERE id=?", (row["id"],)
                    )
                    self.store.db.execute(
                        "UPDATE rt_commands SET status='rejected' WHERE id=?", (row["command_id"],)
                    )
                    self.store.event(
                        self.shift,
                        "review_expired",
                        {
                            "review_id": row["id"],
                            "command_id": row["command_id"],
                            "reason": gate["reason"],
                        },
                    )
                    self.store.db.execute("COMMIT")
                except BaseException:
                    self.store.db.execute("ROLLBACK")
                    raise

    async def tick(self, lateness_ms=0):
        started_tick = time.monotonic()
        async with self.tick_lock:
            if self.lifecycle == "ENDED":
                return
            self.expire_reviews()
            current = self.store.current(self.shift)
            epoch = self.epoch
            rows = self.store.db.execute(
                "SELECT * FROM rt_commands WHERE shift=? AND status='queued' ORDER BY CASE WHEN session='operator.session' THEN 0 ELSE 1 END,rowid LIMIT 64",
                (self.shift,),
            ).fetchall()
            commands, refused = [], []
            subject_selected = False
            for row in rows:
                c = json.loads(row["payload"])
                gate = (
                    self._gate(c, c.get("reviewed", False))
                    if c["actor"] == "subject"
                    else {"outcome": "allow"}
                )
                if gate["outcome"] != "allow":
                    refused.append((c, gate["reason"]))
                    continue
                if c["actor"] == "subject":
                    if subject_selected:
                        continue
                    subject_selected = True
                commands.append(
                    {
                        "command_id": c["command_id"],
                        "call": c["call"],
                        "principal": {"id": c["principal_id"], "role": c["actor"]},
                        "expected_control_revision": c["expected_control_revision"]
                        if c["call"]["operation"] == "loop.set"
                        else None,
                    }
                )
                if commands[-1]["expected_control_revision"] is None:
                    del commands[-1]["expected_control_revision"]
            candidate = await self.worker.request(
                "compute_tick",
                state_bytes=current["bytes"],
                expected_hash=current["hash"],
                commands=commands,
            )
            # Takeover can run during IPC. Nothing was committed; discard and recompute next turn.
            if epoch != self.epoch:
                return
            for row in rows:
                command = json.loads(row["payload"])
                if (
                    command["actor"] == "subject"
                    and any(x["command_id"] == command["command_id"] for x in commands)
                    and self._gate(command, command.get("reviewed", False))["outcome"] != "allow"
                ):
                    return
            raw = candidate["state_bytes"]
            if (
                hashlib.sha256(("peb:plant-state:v1\0" + raw).encode()).hexdigest()
                != candidate["state_hash"]
                or candidate["tick"] != current["tick"] + 1
            ):
                raise ValueError("invalid_candidate")
            self.store.db.execute("BEGIN IMMEDIATE")
            try:
                check = self.store.current(self.shift)
                if (
                    check["hash"] != current["hash"]
                    or check["tick"] != current["tick"]
                    or epoch != self.epoch
                ):
                    raise ValueError("candidate_fenced")
                by_id = {
                    json.loads(r["payload"])["command_id"]: json.loads(r["payload"]) for r in rows
                }
                outcomes = candidate["outcomes"] + [
                    {
                        "command_id": c["command_id"],
                        "status": "rejected",
                        "reason": reason,
                        "before": None,
                        "after": None,
                        "revision_before": 0,
                        "revision_after": 0,
                    }
                    for c, reason in refused
                ]
                effects = []
                for out in outcomes:
                    c = by_id[out["command_id"]]
                    receipt = {
                        "schema_version": "peb.rt.v1",
                        "record_type": "effect_receipt",
                        **{
                            k: c[k]
                            for k in [
                                "shift_id",
                                "subject_session_id",
                                "command_id",
                                "proposal_id",
                                "gate_decision_id",
                                "observation_id",
                            ]
                        },
                        "authenticated_actor": "SUBJECT" if c["actor"] == "subject" else "HUMAN",
                        "status": out["status"],
                        "reason": out["reason"],
                        "commit_tick": candidate["tick"],
                        "sim_time_ms": candidate["board"]["sim_time_ms"],
                        "control_revision_before": out["revision_before"],
                        "control_revision_after": out["revision_after"],
                        "state_hash_before": current["hash"],
                        "state_hash_after": candidate["state_hash"],
                        "operation": c["call"]["operation"],
                        "target": call_target(c["call"]),
                        "control_before": out["before"],
                        "control_after": out["after"],
                        "event_refs": [],
                        "followup_observation_refs": [],
                    }
                    if c["actor"] != "instructor":
                        validate("EffectReceipt", receipt)
                    else:
                        receipt["record_type"] = "instructor_effect"
                    self.store.db.execute(
                        "UPDATE rt_commands SET status=?,receipt=? WHERE id=? AND status='queued'",
                        (out["status"], encode(receipt), c["command_id"]),
                    )
                    self.store.event(
                        self.shift,
                        "effect",
                        receipt,
                        "owner" if c["actor"] == "instructor" else "public",
                    )
                    if (
                        out["status"] == "applied"
                        and c["actor"] == "subject"
                        and c["call"]["operation"] != "view.focus"
                    ):
                        effects.append((call_target(c["call"]), candidate["board"]["sim_time_ms"]))
                        if (
                            c["call"]["operation"] == "loop.set"
                            and out["after"].get("mode") == "MAN"
                            and out["after"].get("op_milli") == 0
                        ):
                            effects.append(
                                (
                                    "protective:" + call_target(c["call"]),
                                    candidate["board"]["sim_time_ms"],
                                )
                            )
                self.store.db.execute(
                    "UPDATE rt_plant_current SET tick=?,bytes=?,hash=? WHERE shift=?",
                    (candidate["tick"], raw, candidate["state_hash"], self.shift),
                )
                self.store.db.execute(
                    "INSERT INTO rt_tick_log VALUES(?,?,?,?,?)",
                    (
                        self.shift,
                        candidate["tick"],
                        encode(commands),
                        candidate["state_hash"],
                        encode(
                            {
                                "commit_started_lateness_ms": round(
                                    lateness_ms + (time.monotonic() - started_tick) * 1000
                                ),
                                "committed_utc": utc(),
                            }
                        ),
                    ),
                )
                self.store.event(
                    self.shift,
                    "tick",
                    {
                        "tick": candidate["tick"],
                        "sim_time_ms": candidate["board"]["sim_time_ms"],
                        "state_hash": candidate["state_hash"],
                        "commit_started_lateness_ms": round(
                            lateness_ms + (time.monotonic() - started_tick) * 1000
                        ),
                    },
                )
                self.store.db.execute("COMMIT")
            except BaseException:
                self.store.db.execute("ROLLBACK")
                raise
            # Completion is measured after FULL synchronous COMMIT, never before IPC.
            completion_ms = round(lateness_ms + (time.monotonic() - started_tick) * 1000)
            self.store.event(
                self.shift,
                "tick_commit_timing",
                {"tick": candidate["tick"], "lateness_ms": completion_ms},
                "owner",
            )
            self.last_effects = [
                (t, when)
                for t, when in self.last_effects + effects
                if candidate["board"]["sim_time_ms"] - when < 60000
            ]
            self.board, self.subject = candidate["board"], candidate["subject"]
            if effects:
                self.phase = "VERIFYING"
            return completion_ms

    async def start_clock(self):
        if not self.shift or self.lifecycle == "ENDED":
            raise ValueError("no_running_shift")
        self.clock_running = True
        self.clock_status = "RUNNING"
        if self.clock_task is None or self.clock_task.done():
            self.clock_task = asyncio.create_task(self._clock())

    async def _clock(self):
        due = asyncio.get_running_loop().time() + 0.5
        while self.clock_running and not self.closed:
            await asyncio.sleep(max(0, due - asyncio.get_running_loop().time()))
            if not self.clock_running:
                break
            now = asyncio.get_running_loop().time()
            debt = now - due
            if not self.clock_health(round(debt * 1000)):
                break
            try:
                completion_ms = await self.tick(debt * 1000)
                if completion_ms is not None and not self.clock_health(completion_ms):
                    break
            except Exception as exc:  # noqa: BLE001 — every candidate failure freezes the durable world
                self.pause_infrastructure(type(exc).__name__, round(debt * 1000))
                break
            due += 0.5
            await asyncio.sleep(0)
            if self.lifecycle in {"ACTIVE", "HUMAN_CONTROL"} and not self.grant.get("revoked"):
                if time.time() >= self.grant["expires_wall"]:
                    self.agent_control("pause", reason="grant_expired")
                else:
                    self.grant["lease_wall"] = min(time.time() + 60, self.grant["expires_wall"])
                    if (
                        self.provider
                        and (self.subject_task is None or self.subject_task.done())
                        and time.monotonic() - self.last_call >= 10
                    ):
                        self.subject_task = asyncio.create_task(self.decide())

    def clock_health(self, debt_ms):
        if debt_ms > self.policy["clock"]["pause_debt_ms"]:
            self.pause_infrastructure("clock_debt", debt_ms)
            return False
        self.clock_status = (
            "CLOCK_DEGRADED" if debt_ms > self.policy["clock"]["degraded_debt_ms"] else "RUNNING"
        )
        return True

    def pause_infrastructure(self, reason, debt_ms=0):
        self.clock_running = False
        self.clock_status = "INFRA_PAUSED"
        self.lifecycle = "INFRA_PAUSED"
        self.failure = reason
        self.epoch += 1
        try:
            self._save_shift()
            self.store.event(
                self.shift, "infrastructure_gap", {"reason": reason, "debt_ms": debt_ms}
            )
        except Exception as exc:  # noqa: BLE001 — storage may be unavailable at this boundary
            self.failure = reason + "; record unavailable: " + type(exc).__name__

    def agent_control(self, operation, reason="operator"):
        if self.lifecycle == "ENDED":
            raise ValueError("shift_ended")
        if operation not in {"pause", "resume", "end"}:
            raise ValueError("unknown_agent_control")
        self.epoch += 1
        if operation == "resume":
            predecessor = self.session
            self.session = ident("subject")
            self.grant.update(
                session=self.session,
                revoked=False,
                expires_wall=time.time() + self.config.wall_duration_s,
                lease_wall=time.time() + 60,
            )
            self.lifecycle = "HUMAN_CONTROL" if self.store.owners(self.shift) else "ACTIVE"
            self.store.event(
                self.shift,
                "subject_handoff",
                {
                    "predecessor_session_id": predecessor,
                    "subject_session_id": self.session,
                    "calls_used": self.calls,
                },
            )
        elif operation in {"pause", "end"}:
            self.grant["revoked"] = True
            self.lifecycle = "ENDED" if operation == "end" else "AGENT_DEGRADED"
            if operation == "end":
                self.clock_running = False
                self.clock_status = "STOPPED"
        else:
            raise ValueError("unknown_agent_control")
        self._save_shift()
        self.store.event(
            self.shift,
            "agent_control",
            {
                "operation": operation,
                "reason": reason,
                "authority_epoch": self.epoch,
                "calls_used": self.calls,
            },
        )

    async def decide(self):
        if self.lifecycle == "ENDED" or self.grant.get("revoked") or self.provider is None:
            return
        try:
            await self._decide()
        except Exception as exc:  # noqa: BLE001 — request construction must also fail closed
            if self.lifecycle != "ENDED":
                self.phase = "REQUEST_FAILED"
                self.store.event(
                    self.shift,
                    "provider_failure",
                    {"reason": type(exc).__name__, "call": self.calls},
                )

    async def _decide(self):
        if self.calls >= self.config.max_calls:
            self.agent_control("pause", "budget_exhausted")
            return
        self.calls += 1
        self.last_call = time.monotonic()
        epoch, session = self.epoch, self.session
        self.phase = "OBSERVING"
        observation = self.observe()
        from .prompt import build_messages

        messages = build_messages(observation, self.policy, self.store, self.shift)
        if sum(len(m["content"]) for m in messages) > 60000:
            raise ValueError("input_limit_exceeded")
        request = RTModelRequest(
            run_id=self.shift,
            subject_session_id=session,
            step=self.calls,
            provider_kind=self.config.provider,
            model=self.config.model,
            messages=[ModelMessage(**m) for m in messages],
            response_schema={"$defs": SCHEMA["$defs"], "$ref": "#/$defs/SubjectDecision"},
            limits=Limits(
                max_model_calls=1,
                max_output_tokens=self.config.max_output_tokens,
                request_timeout_s=12,
                decision_ceiling_bytes=16384,
            ),
            input_hash=digest("peb:rt-input:v1", messages),
        )
        self.store.event(
            self.shift,
            "provider_request",
            {
                "subject_session_id": session,
                "call": self.calls,
                "input_hash": request.input_hash,
                "observation_id": observation["observation_id"],
                "messages": messages,
            },
            "owner",
        )
        self.phase = "DECIDING"
        started = time.monotonic()
        try:
            async with asyncio.timeout(12):
                response = await self.provider.generate(request)
            if self.lifecycle == "ENDED":
                return
            self.store.event(
                self.shift,
                "provider_response",
                {
                    "call": self.calls,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "response": response.model_dump(mode="json"),
                    "diagnostics": self.provider.diagnostics()
                    if hasattr(self.provider, "diagnostics")
                    else {},
                },
                "owner",
            )
            if (
                epoch != self.epoch
                or session != self.session
                or self.grant.get("revoked")
                or self.lifecycle == "ENDED"
            ):
                self.phase = "DISCARDED"
                return
            if response.error or response.model_resolved != self.config.model:
                raise ValueError("provider_response_unusable")
            decision = Decision.parse(response.content)
            self.store.event(
                self.shift,
                "decision",
                {
                    "observation_id": observation["observation_id"],
                    "decision": decision.model_dump(exclude_none=True),
                },
            )
            if decision.kind == "act":
                self.phase = "PROPOSED"
                self.submit(decision.call.model_dump(), observation)
            else:
                self.phase = decision.kind.upper()
        except TimeoutError:
            self.phase = "MODEL_TIMEOUT"
            if self.lifecycle != "ENDED":
                self.store.event(
                    self.shift,
                    "provider_failure",
                    {
                        "reason": "deadline",
                        "call": self.calls,
                        "diagnostics": self.provider.diagnostics()
                        if hasattr(self.provider, "diagnostics")
                        else {},
                    },
                )
        except Exception as exc:  # noqa: BLE001 — untrusted provider failures are retained as closed codes
            self.phase = "INVALID_RESPONSE"
            if self.lifecycle != "ENDED":
                self.store.event(
                    self.shift,
                    "provider_failure",
                    {"reason": type(exc).__name__, "call": self.calls},
                )

    async def close(self):
        self.closed = True
        self.clock_running = False
        for task in [self.clock_task, self.subject_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self.worker.close()
        if self.provider and hasattr(self.provider, "close"):
            await self.provider.close()
        self.store.close()

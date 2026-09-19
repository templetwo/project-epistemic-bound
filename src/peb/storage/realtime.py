"""Isolated real-time state and append-only record in one SQLite transaction domain."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ..rt_contracts import encode


class RTStore:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.db = sqlite3.connect(root / "realtime.sqlite", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS rt_shifts(id TEXT PRIMARY KEY, config TEXT NOT NULL, lifecycle TEXT NOT NULL, epoch INTEGER NOT NULL, session TEXT NOT NULL, policy TEXT NOT NULL, grant_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rt_plant_current(shift TEXT PRIMARY KEY REFERENCES rt_shifts(id), tick INTEGER NOT NULL, bytes TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rt_checkpoints(shift TEXT NOT NULL, tick INTEGER NOT NULL, bytes TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(shift,tick));
        CREATE TABLE IF NOT EXISTS rt_tick_log(shift TEXT NOT NULL, tick INTEGER NOT NULL, inputs TEXT NOT NULL, hash TEXT NOT NULL, timing TEXT NOT NULL, PRIMARY KEY(shift,tick));
        CREATE TABLE IF NOT EXISTS rt_records(seq INTEGER PRIMARY KEY AUTOINCREMENT, shift TEXT NOT NULL, kind TEXT NOT NULL, visibility TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rt_commands(id TEXT PRIMARY KEY, shift TEXT NOT NULL, session TEXT NOT NULL, idem TEXT NOT NULL, hash TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT, UNIQUE(shift,session,idem));
        CREATE TABLE IF NOT EXISTS rt_observations(id TEXT PRIMARY KEY, shift TEXT NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL, created_wall REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rt_reviews(id TEXT PRIMARY KEY, shift TEXT NOT NULL, command_id TEXT NOT NULL, status TEXT NOT NULL, digest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rt_control_ownership(shift TEXT NOT NULL, target TEXT NOT NULL, owner TEXT NOT NULL, PRIMARY KEY(shift,target));
        CREATE TABLE IF NOT EXISTS rt_outbox(seq INTEGER PRIMARY KEY, shift TEXT NOT NULL, visibility TEXT NOT NULL, payload TEXT NOT NULL);
        """)

    def event(self, shift, kind, payload, visibility="public"):
        wire = encode(payload)
        previous = self.db.execute(
            "SELECT hash FROM rt_records ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev = previous[0] if previous else "0" * 64
        h = hashlib.sha256(
            (
                "peb:rt-event:v1\0"
                + prev
                + "\0"
                + shift
                + "\0"
                + kind
                + "\0"
                + visibility
                + "\0"
                + wire
            ).encode()
        ).hexdigest()
        cursor = self.db.execute(
            "INSERT INTO rt_records(shift,kind,visibility,payload,previous_hash,hash) VALUES(?,?,?,?,?,?)",
            (shift, kind, visibility, wire, prev, h),
        )
        seq = cursor.lastrowid
        self.db.execute(
            "INSERT INTO rt_outbox VALUES(?,?,?,?)",
            (seq, shift, visibility, encode({"seq": seq, "kind": kind, "payload": payload})),
        )
        return seq

    def current(self, shift):
        row = self.db.execute("SELECT * FROM rt_plant_current WHERE shift=?", (shift,)).fetchone()
        if row is None:
            raise ValueError("unknown_shift")
        return dict(row)

    def owners(self, shift):
        return {
            r[0]: r[1]
            for r in self.db.execute(
                "SELECT target,owner FROM rt_control_ownership WHERE shift=?", (shift,)
            )
        }

    def command(self, command_id):
        row = self.db.execute("SELECT * FROM rt_commands WHERE id=?", (command_id,)).fetchone()
        if row is None:
            raise ValueError("unknown_command")
        return {**dict(row), "receipt": json.loads(row["receipt"]) if row["receipt"] else None}

    def close(self):
        self.db.close()

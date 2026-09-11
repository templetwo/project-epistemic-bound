"""Shared fixtures. Every test gets a temporary state root (BUILD_SPEC §4.3, ISO-02).

ISO-02 guard (Anthony, 2026-09-11: "prove tests leave protected state unchanged whether that state starts
absent or populated; do not delete or modify the real operator database to satisfy the test"):
- the whole session runs with PEB_STATE_ROOT pointing at a session-temporary root, so a test that forgets the
  `state_root` fixture still cannot land on the operator's root;
- the operator's protected files (database + WAL/SHM, HMAC key, operator secret, lock files) are snapshotted
  (existence, size, sha256) before the first test and compared after the last; any difference fails the session
  loudly, and a test may assert `operator_state.unchanged()` at any point. Absent files are a valid snapshot.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from peb.config import DEFAULT_STATE_ROOT

PROTECTED_RELATIVE = ("peb.sqlite", "peb.sqlite-wal", "peb.sqlite-shm", "keys/development_local_hmac.key",
                      "operator.secret", "supervisor.lock", "inference.lock")


def _fingerprint(path: Path) -> tuple[bool, int, str] | None:
    """(exists, size, sha256) or None for an absent path. Never writes."""
    if not path.exists():
        return None
    if path.is_dir():
        names = sorted(p.name for p in path.iterdir())
        return (True, len(names), hashlib.sha256("\n".join(names).encode()).hexdigest())
    data = path.read_bytes()
    return (True, len(data), hashlib.sha256(data).hexdigest())


def snapshot_protected(root: Path) -> dict[str, tuple[bool, int, str] | None]:
    root = root.expanduser()
    return {rel: _fingerprint(root / rel) for rel in PROTECTED_RELATIVE} | {"<root>": _fingerprint(root)}


@dataclass(frozen=True)
class OperatorStateGuard:
    root: Path
    before: dict[str, tuple[bool, int, str] | None]

    def diff(self) -> dict[str, tuple]:
        now = snapshot_protected(self.root)
        return {k: (self.before.get(k), now.get(k)) for k in set(self.before) | set(now) if self.before.get(k) != now.get(k)}

    def unchanged(self) -> bool:
        return not self.diff()


@pytest.fixture(scope="session", autouse=True)
def _operator_state_guard_session():
    """Snapshot before the first test; redirect the default state root for the whole session; verify after the last."""
    guard = OperatorStateGuard(root=DEFAULT_STATE_ROOT.expanduser(), before=snapshot_protected(DEFAULT_STATE_ROOT))
    previous = os.environ.get("PEB_STATE_ROOT")
    with tempfile.TemporaryDirectory(prefix="peb-test-session-root-") as session_root:
        os.environ["PEB_STATE_ROOT"] = str(Path(session_root) / "state")
        try:
            yield guard
        finally:
            if previous is None:
                os.environ.pop("PEB_STATE_ROOT", None)
            else:
                os.environ["PEB_STATE_ROOT"] = previous
    diff = guard.diff()
    assert not diff, f"ISO-02: the test session changed protected operator state under {guard.root}: {diff}"


@pytest.fixture
def operator_state(_operator_state_guard_session) -> OperatorStateGuard:
    """The session guard, for tests that want to assert the operator root is untouched at a specific point."""
    return _operator_state_guard_session


@pytest.fixture
def state_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setenv("PEB_STATE_ROOT", str(root))
    monkeypatch.delenv("PEB_OLLAMA_MODEL", raising=False)
    # Point the provider probe at a closed loopback port so tests never touch a real server.
    monkeypatch.setenv("PEB_OLLAMA_ENDPOINT", "http://127.0.0.1:9")
    return root

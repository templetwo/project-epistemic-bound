"""ISO-02 guard behaviour, exercised on TEMPORARY roots only (never the operator's)."""
from __future__ import annotations

import os
from pathlib import Path

from tests.conftest import PROTECTED_RELATIVE, OperatorStateGuard, snapshot_protected


def test_absent_root_is_a_valid_unchanged_snapshot(tmp_path: Path):
    root = tmp_path / "absent-operator-root"
    g = OperatorStateGuard(root=root, before=snapshot_protected(root))
    assert g.unchanged() and all(v is None for v in g.before.values())


def test_populated_root_unchanged_when_untouched_and_changed_when_written(tmp_path: Path):
    root = tmp_path / "operator-root"
    (root / "keys").mkdir(parents=True)
    (root / "peb.sqlite").write_bytes(b"sqlite bytes" * 100)
    (root / "keys" / "development_local_hmac.key").write_bytes(b"k" * 32)
    (root / "operator.secret").write_text("s" * 64)
    g = OperatorStateGuard(root=root, before=snapshot_protected(root))
    assert g.unchanged()
    (root / "peb.sqlite").write_bytes(b"sqlite bytes" * 101)  # a write the tests must never do to the real root
    d = g.diff()
    assert not g.unchanged() and set(d) == {"peb.sqlite"} and d["peb.sqlite"][0][1] != d["peb.sqlite"][1][1]
    (root / "peb.sqlite-wal").write_bytes(b"w")  # a new protected file appearing is also a change
    assert "peb.sqlite-wal" in g.diff()
    (root / "operator.secret").unlink()  # and a deletion
    assert "operator.secret" in g.diff()


def test_session_redirects_the_default_state_root_away_from_the_operator(operator_state):
    assert "peb-test-session-root-" in os.environ["PEB_STATE_ROOT"]
    assert Path(os.environ["PEB_STATE_ROOT"]).expanduser() != operator_state.root
    assert set(PROTECTED_RELATIVE) >= {"peb.sqlite", "keys/development_local_hmac.key", "operator.secret"}
    assert operator_state.unchanged(), operator_state.diff()

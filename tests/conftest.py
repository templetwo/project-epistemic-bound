"""Shared fixtures. Every test gets a temporary state root (BUILD_SPEC §4.3, ISO-02)."""
from __future__ import annotations

import pytest


@pytest.fixture
def state_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setenv("PEB_STATE_ROOT", str(root))
    monkeypatch.delenv("PEB_OLLAMA_MODEL", raising=False)
    # Point the provider probe at a closed loopback port so tests never touch a real server.
    monkeypatch.setenv("PEB_OLLAMA_ENDPOINT", "http://127.0.0.1:9")
    return root

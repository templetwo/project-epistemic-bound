"""Operator configuration and state-root resolution (BUILD_SPEC §6, §9.1, §15.3).

Precedence: explicit argument > environment > default. Tests must pass an explicit
temporary state root; nothing here ever defaults a test to the operator's database.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_ROOT = Path("~/.local/share/project-epistemic-bound")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
SIGNING_MODE = "development_local_hmac"  # §11.1 — never "hardware-backed"


@dataclass(frozen=True)
class AppConfig:
    state_root: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    ollama_endpoint: str = DEFAULT_OLLAMA_ENDPOINT
    ollama_model: str | None = None
    signing_mode: str = SIGNING_MODE


def resolve_state_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    raw = explicit if explicit is not None else os.environ.get("PEB_STATE_ROOT") or DEFAULT_STATE_ROOT
    return Path(raw).expanduser()


def load_config(state_root: str | os.PathLike[str] | None = None) -> AppConfig:
    env = os.environ
    port_raw = env.get("PEB_PORT")
    port = int(port_raw) if port_raw and port_raw.isdigit() else DEFAULT_PORT
    return AppConfig(
        state_root=resolve_state_root(state_root),
        host=env.get("PEB_HOST", DEFAULT_HOST),
        port=port,
        ollama_endpoint=env.get("PEB_OLLAMA_ENDPOINT", DEFAULT_OLLAMA_ENDPOINT),
        ollama_model=env.get("PEB_OLLAMA_MODEL") or None,
    )

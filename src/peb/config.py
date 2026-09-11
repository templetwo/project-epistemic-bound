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
    deepseek_endpoint: str = "https://api.deepseek.com"  # explicit https endpoint; the key is NEVER a config field
    deepseek_api_key_env: str = "DEEPSEEK_API_KEY"       # the environment variable NAME the provider reads


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
        deepseek_endpoint=env.get("PEB_DEEPSEEK_ENDPOINT", "https://api.deepseek.com"),
        ollama_model=env.get("PEB_OLLAMA_MODEL") or None,
    )


OPERATOR_SECRET_FILE = "operator.secret"


def load_or_create_operator_secret(state_root: str | os.PathLike[str]) -> str:
    """The workroom's operator credential lives ONLY in the state root (0600), never in source, logs or
    model input (BUILD_SPEC §16). Created on first `peb serve`; rotated by deleting the file."""
    import secrets

    path = Path(state_root) / OPERATOR_SECRET_FILE
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) < 32:
            raise RuntimeError(f"operator secret at {path} is too short; delete it to regenerate")
        return value
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        value = secrets.token_hex(32)
        f.write(value + "\n")
    return value

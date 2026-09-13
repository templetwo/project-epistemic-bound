"""Process-memory DeepSeek credentials, isolated by service request and never persisted.

Context snapshots flow through async calls and asyncio.to_thread without mutating
os.environ. Providers retain their construction snapshot when the operator clears
or replaces the service's override. Every stored secret has a redacted repr.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

CredentialSource = Literal["secure_input", "environment", "absent"]


@dataclass(frozen=True)
class CredentialSnapshot:
    secret: SecretStr | None
    source: CredentialSource


_active_credential: ContextVar[CredentialSnapshot | None] = ContextVar("peb_deepseek_credential", default=None)


def snapshot_credential(override: SecretStr | None, api_key_env: str = "DEEPSEEK_API_KEY") -> CredentialSnapshot:
    """Read this service's explicit override or environment, never an enclosing service's context."""
    if override is not None:
        return CredentialSnapshot(override, "secure_input")
    value = os.environ.get(api_key_env, "") or ""
    return CredentialSnapshot(SecretStr(value), "environment") if value else CredentialSnapshot(None, "absent")


@contextmanager
def credential_scope(snapshot: CredentialSnapshot):
    token = _active_credential.set(snapshot)
    try:
        yield
    finally:
        _active_credential.reset(token)


def resolve_credential(api_key_env: str = "DEEPSEEK_API_KEY") -> CredentialSnapshot:
    """A provider captures one effective key; CLI callers outside a service keep environment behavior."""
    snapshot = _active_credential.get()
    return snapshot if snapshot is not None else snapshot_credential(None, api_key_env)


def credential_status(snapshot: CredentialSnapshot) -> dict[str, str | bool]:
    return {
        "provider": "deepseek",
        "key": "present" if snapshot.secret is not None and snapshot.secret.get_secret_value() else "absent",
        "source": snapshot.source,
        "lifetime": "server_process",
        "can_clear": snapshot.source == "secure_input",
        "note": "Secure input stays in this server's memory until cleared or the server restarts. "
                "Clearing removes only that override; an environment key remains available. "
                "Operator login/logout does not change provider credentials. Active requests keep their "
                "captured key. Saving or clearing makes no provider request.",
    }

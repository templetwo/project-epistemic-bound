"""Verification against a stored chain and optional trusted checkpoint (BUILD_SPEC §14.2).

S2 storage always supplies manifest_hash and the development HMAC key. Absent-key
checks remain unchecked evidence, never authenticated (INTERFACES §9).
"""
from __future__ import annotations

from ..contracts import Checkpoint, VerificationResult
from ..errors import ErrorCode, PebError
from ..storage.repository import SqliteRepository


def verify_run(repo: SqliteRepository, run_id: str, checkpoint: Checkpoint | None = None) -> VerificationResult:
    if not repo.run_exists(run_id):
        raise PebError(ErrorCode.invalid_input, "unknown run_id", {"run_id": run_id})
    if checkpoint is None:
        checkpoint = repo.latest_checkpoint(run_id)
    return repo.verify(run_id, checkpoint)

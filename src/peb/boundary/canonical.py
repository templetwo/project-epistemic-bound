"""Canonicalization and digests (BUILD_SPEC §11.2). FROZEN at the S1 contract commit.

Rules: deterministic UTF-8 JSON, sorted keys, compact separators, no NaN/Infinity,
no floating-point values in authorization-critical fields, duplicate keys rejected
upstream by `contracts.strict_json_loads`. Every digest carries a schema/domain
prefix so an event hash can never be confused with an approval digest.

Owner after freeze: seat 3/3 (boundary) may EXTEND this module; changing an existing
domain string or the byte layout is a contract change and needs a reviewed amendment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
from typing import Any

DOMAIN_EVENT = "peb:event:v1"
DOMAIN_PROPOSAL = "peb:proposal:v1"
DOMAIN_APPROVAL = "peb:approval:v1"
DOMAIN_CHECKPOINT = "peb:checkpoint:v1"
DOMAIN_SNAPSHOT = "peb:snapshot:v1"
DOMAIN_MODEL_INPUT = "peb:model-input:v1"
DOMAIN_RESOURCE = "peb:resource:v1"


class CanonicalizationError(ValueError):
    pass


def _check(obj: Any, *, forbid_floats: bool, path: str = "$") -> None:
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise CanonicalizationError(f"non-finite float at {path}")
        if forbid_floats:
            raise CanonicalizationError(f"float not allowed in authorization-critical field at {path}")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonicalizationError(f"non-string key at {path}")
            _check(v, forbid_floats=forbid_floats, path=f"{path}.{k}")
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check(v, forbid_floats=forbid_floats, path=f"{path}[{i}]")
        return
    raise CanonicalizationError(f"non-JSON value {type(obj).__name__} at {path}")


def canonical_json(obj: Any, *, forbid_floats: bool = False) -> bytes:
    """Deterministic bytes for `obj`. Input must already be JSON-compatible (use model_dump(mode='json'))."""
    _check(obj, forbid_floats=forbid_floats)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(domain: str, obj: Any, *, forbid_floats: bool = False) -> str:
    """SHA-256 over `domain || 0x00 || canonical_json(obj)`; hex."""
    h = hashlib.sha256()
    h.update(domain.encode("utf-8"))
    h.update(b"\x00")
    h.update(canonical_json(obj, forbid_floats=forbid_floats))
    return h.hexdigest()


def proposal_digest(run_id: str, subject_session_id: str, step: int, call: dict[str, Any]) -> str:
    """Canonical action digest bound to run, session, step and the exact tool call (§11.1)."""
    return digest(DOMAIN_PROPOSAL, {"run_id": run_id, "subject_session_id": subject_session_id,
                                    "step": step, "call": call}, forbid_floats=True)


def hmac_sign(key: bytes, domain: str, obj: Any) -> str:
    """development_local_hmac signature (§11.1). Not hardware-backed, not a human signature."""
    body = domain.encode("utf-8") + b"\x00" + canonical_json(obj, forbid_floats=True)
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def hmac_verify(key: bytes, domain: str, obj: Any, signature: str) -> bool:
    return hmac.compare_digest(hmac_sign(key, domain, obj), signature)

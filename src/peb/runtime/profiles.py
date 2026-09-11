"""Subject profiles (BUILD_SPEC §16.2). Seat 1/3 owns assembly; text comes from config/profiles/*.json.

A profile is configuration, not law (ADR-006). Text marked [PLACEHOLDER …] is not the source
contract and must never be reported as it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..boundary.canonical import DOMAIN_SNAPSHOT, digest
from ..contracts import PreactionProtocol, strict_json_loads
from ..errors import ErrorCode, PebError

PROFILE_ROOT = Path(__file__).resolve().parents[3] / "config" / "profiles"
PROFILE_IDS = ("candidate_v1", "baseline", "tone_only", "contract_only", "placebo")


@dataclass(frozen=True)
class Profile:
    profile_id: str
    status: str
    text: str
    preaction_protocol: PreactionProtocol
    source: str
    placeholder: bool

    @property
    def hash(self) -> str:
        return digest(DOMAIN_SNAPSHOT, {"profile_id": self.profile_id, "text": self.text,
                                        "preaction_protocol": str(self.preaction_protocol)})


def load_profile(profile_id: str, *, root: Path = PROFILE_ROOT) -> Profile:
    if profile_id not in PROFILE_IDS:
        raise PebError(ErrorCode.invalid_input, f"unknown profile {profile_id!r}", {"profiles": list(PROFILE_IDS)})
    path = root / f"{profile_id}.json"
    if not path.is_file():
        raise PebError(ErrorCode.not_implemented, f"profile {profile_id!r} is not written yet (S5)",
                       {"path": str(path)})
    data = strict_json_loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "profile_id", "status", "source", "preaction_protocol", "text"}
    if not isinstance(data, dict) or set(data) != required or data["profile_id"] != profile_id:
        raise PebError(ErrorCode.invalid_input, "profile file has the wrong shape", {"path": str(path)})
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise PebError(ErrorCode.invalid_input, "profile schema_version must be the integer 1")
    return Profile(profile_id=profile_id, status=str(data["status"]), text=str(data["text"]),
                   preaction_protocol=PreactionProtocol(data["preaction_protocol"]), source=str(data["source"]),
                   placeholder="[PLACEHOLDER" in data["text"])


def profile_catalog(*, root: Path = PROFILE_ROOT) -> list[dict]:
    out = []
    for pid in PROFILE_IDS:
        path = root / f"{pid}.json"
        if path.is_file():
            p = load_profile(pid, root=root)
            out.append({"profile_id": pid, "status": p.status, "preaction_protocol": str(p.preaction_protocol),
                        "placeholder_text": p.placeholder, "hash": p.hash, "source": p.source})
        else:
            out.append({"profile_id": pid, "status": "not_written", "note": "S5"})
    return out


__all__ = ["PROFILE_IDS", "Profile", "json", "load_profile", "profile_catalog"]

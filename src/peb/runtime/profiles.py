"""Subject profiles (BUILD_SPEC §16.2). Seat 1/3 owns assembly; text comes from config/profiles/*.json.

A profile is configuration, not law (ADR-006). Text marked [PLACEHOLDER …] is not the source contract and
must never be reported as it. The four framing arms share the A0 text as a prefix; the ADDITION after it is
the whole treatment, and `check_arm_hygiene` (EVAL-03) checks that no candidate/contract wording leaks into
A0/A1/A3 and that the placebo addition carries no confidentiality/truthfulness wording. Lengths are recorded
exactly in characters and words; token counts are measured per run from the provider's own accounting
(ModelResponse.prompt_tokens), not estimated here.
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
ARMS = {"baseline": "A0", "tone_only": "A1", "contract_only": "A2", "placebo": "A3", "candidate_v1": "candidate"}
# Statuses that may NOT be run as a model arm: the text is not the treatment it names.
NOT_RUNNABLE_STATUSES = frozenset({"awaiting_source_text", "not_written"})
# EVAL-03: candidate/contract wording that must be absent from the A0/A1/A3 arms (whole text).
CONTRACT_MARKERS = ("commitment", "undertaking", "declaration", "no-framing-exemption", "integrity contract")
# §16.2: the placebo addition must not use confidentiality/truthfulness wording (checked on the ADDITION only,
# because the shared A0 text legitimately says "report").
TRUTHFULNESS_WORDS = ("confiden", "truth", "honest", "accura", "conceal", "disclos", "integrity", "correct",
                      "hide", "mislead", "deceiv", "report")


@dataclass(frozen=True)
class Profile:
    profile_id: str
    status: str
    text: str
    preaction_protocol: PreactionProtocol
    source: str
    placeholder: bool
    arm: str
    notes: str = ""

    @property
    def hash(self) -> str:
        return digest(DOMAIN_SNAPSHOT, {"profile_id": self.profile_id, "text": self.text,
                                        "preaction_protocol": str(self.preaction_protocol)})

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def runnable(self) -> bool:
        return self.status not in NOT_RUNNABLE_STATUSES


def load_profile(profile_id: str, *, root: Path = PROFILE_ROOT) -> Profile:
    if profile_id not in PROFILE_IDS:
        raise PebError(ErrorCode.invalid_input, f"unknown profile {profile_id!r}", {"profiles": list(PROFILE_IDS)})
    path = root / f"{profile_id}.json"
    if not path.is_file():
        raise PebError(ErrorCode.not_implemented, f"profile {profile_id!r} is not written yet (S5)",
                       {"path": str(path)})
    data = strict_json_loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "profile_id", "status", "source", "preaction_protocol", "text"}
    optional = {"arm", "notes"}
    if not isinstance(data, dict) or not required <= set(data) <= required | optional or data["profile_id"] != profile_id:
        raise PebError(ErrorCode.invalid_input, "profile file has the wrong shape", {"path": str(path)})
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise PebError(ErrorCode.invalid_input, "profile schema_version must be the integer 1")
    arm = str(data.get("arm", ARMS[profile_id]))
    if arm != ARMS[profile_id]:
        raise PebError(ErrorCode.invalid_input, f"profile {profile_id!r} declares arm {arm!r}; §16.2 assigns {ARMS[profile_id]!r}")
    return Profile(profile_id=profile_id, status=str(data["status"]), text=str(data["text"]),
                   preaction_protocol=PreactionProtocol(data["preaction_protocol"]), source=str(data["source"]),
                   placeholder="[PLACEHOLDER" in data["text"], arm=arm, notes=str(data.get("notes", "")))


def require_runnable(profile: Profile) -> Profile:
    """A model run on a profile whose text is not the treatment it names would be labelled as that arm and
    would be a lie in the data. Refuse; the catalog says why."""
    if not profile.runnable:
        raise PebError(ErrorCode.invalid_input,
                       f"profile {profile.profile_id!r} ({profile.arm}) is {profile.status}: it cannot be run as a model arm",
                       {"profile_id": profile.profile_id, "status": profile.status, "source": profile.source})
    return profile


def addition_after_a0(profile: Profile, a0: Profile) -> str | None:
    """The framing arms are A0 + an addition; None when the profile does not extend A0 (candidate_v1)."""
    if profile.profile_id == a0.profile_id:
        return ""
    return profile.text[len(a0.text):] if profile.text.startswith(a0.text) else None


def check_arm_hygiene(*, root: Path = PROFILE_ROOT) -> list[dict]:
    """EVAL-03 findings over the written profiles. Empty list = the arms differ exactly as declared."""
    findings: list[dict] = []
    written = {pid: load_profile(pid, root=root) for pid in PROFILE_IDS if (root / f"{pid}.json").is_file()}
    a0 = written.get("baseline")
    if a0 is None:
        return [{"profile_id": "baseline", "finding": "A0 baseline is not written; the arms have no common prefix"}]
    for pid in ("tone_only", "contract_only", "placebo"):
        p = written.get(pid)
        if p is None:
            continue
        if addition_after_a0(p, a0) is None:
            findings.append({"profile_id": pid, "finding": "text does not start with the A0 baseline text"})
        if p.preaction_protocol is not a0.preaction_protocol:
            findings.append({"profile_id": pid, "finding": "framing arms must share A0's preaction_protocol (§16.2: observe in all four)"})
    for pid in ("baseline", "tone_only", "placebo"):
        p = written.get(pid)
        if p is None:
            continue
        low = p.text.lower()
        for marker in CONTRACT_MARKERS:
            if marker in low:
                findings.append({"profile_id": pid, "finding": f"contract wording {marker!r} present in a control arm (EVAL-03)"})
    placebo = written.get("placebo")
    if placebo is not None:
        addition = (addition_after_a0(placebo, a0) or "").lower()
        for word in TRUTHFULNESS_WORDS:
            if word in addition:
                findings.append({"profile_id": "placebo", "finding": f"placebo addition uses truthfulness/confidentiality wording {word!r} (§16.2)"})
    for pid in ("candidate_v1", "contract_only"):
        p = written.get(pid)
        if p is not None and not any(m in p.text.lower() for m in CONTRACT_MARKERS):
            findings.append({"profile_id": pid, "finding": "declares contract content but carries none of the contract markers"})
    return findings


def profile_catalog(*, root: Path = PROFILE_ROOT) -> list[dict]:
    out = []
    a0 = load_profile("baseline", root=root) if (root / "baseline.json").is_file() else None
    for pid in PROFILE_IDS:
        path = root / f"{pid}.json"
        if path.is_file():
            p = load_profile(pid, root=root)
            addition = addition_after_a0(p, a0) if a0 is not None else None
            out.append({"profile_id": pid, "arm": p.arm, "status": p.status, "runnable": p.runnable,
                        "preaction_protocol": str(p.preaction_protocol), "placeholder_text": p.placeholder,
                        "chars": p.chars, "words": p.words,
                        "addition_chars": len(addition) if addition is not None else None,
                        "addition_words": len(addition.split()) if addition is not None else None,
                        "hash": p.hash, "source": p.source, "notes": p.notes})
        else:
            out.append({"profile_id": pid, "arm": ARMS[pid], "status": "not_written", "runnable": False, "note": "S5"})
    return out


__all__ = ["ARMS", "PROFILE_IDS", "Profile", "addition_after_a0", "check_arm_hygiene", "json", "load_profile",
           "profile_catalog", "require_runnable"]

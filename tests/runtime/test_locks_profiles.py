"""§9.1 OS-held locks and §16.2 profile loading."""
from __future__ import annotations

import pytest

from peb.errors import ErrorCode, PebError
from peb.runtime.locks import InferenceLock, SupervisorLock
from peb.runtime.profiles import PROFILE_IDS, load_profile, profile_catalog


def test_supervisor_lock_is_exclusive_per_state_root_and_released(tmp_path):
    a = SupervisorLock(tmp_path / "state")
    b = SupervisorLock(tmp_path / "state")
    with a:
        assert a.held
        with pytest.raises(PebError) as ei:
            b.acquire()
        assert ei.value.code == ErrorCode.busy and ei.value.detail["state"] == "state_busy"
    assert not a.held
    with b:  # released by exit, not by any PID heuristic
        assert b.held


def test_inference_lock_is_machine_wide_across_state_roots(tmp_path):
    lock_path = tmp_path / "inference.lock"
    first = InferenceLock(lock_path)
    second = InferenceLock(lock_path)
    with first, pytest.raises(PebError, match="inference"):
        second.acquire()
    with second:
        pass


def test_profiles_load_with_honest_placeholder_marking():
    cand = load_profile("candidate_v1")
    assert str(cand.preaction_protocol) == "require" and cand.placeholder is False  # G1 C1–C6 supplied 2026-09-11
    base = load_profile("baseline")
    assert str(base.preaction_protocol) == "observe" and base.placeholder is False
    assert cand.hash != base.hash and len(cand.hash) == 64
    with pytest.raises(PebError) as ei:
        load_profile("not-a-profile")
    assert ei.value.code == ErrorCode.invalid_input
    placebo = load_profile("placebo")  # length-matched to the A2 addition once the contract text arrived
    assert placebo.status == "matched" and placebo.placeholder is False
    with pytest.raises(PebError) as ei2:
        load_profile("baseline", root=pytest.importorskip("pathlib").Path("/nonexistent-profile-root"))
    assert ei2.value.code == ErrorCode.not_implemented  # a missing file is still not_implemented, never a default
    cat = {p["profile_id"]: p for p in profile_catalog()}
    assert set(cat) == set(PROFILE_IDS) and cat["tone_only"]["status"] == "control"
    assert cat["candidate_v1"]["placeholder_text"] is False


# ----------------------------------------------------------------------------- §16.2 arms (S5, seat 1/3)

def test_all_five_profiles_load_with_their_declared_arms_and_statuses():
    from peb.runtime.profiles import (
        ARMS,
        check_arm_hygiene,
        load_profile,
        profile_catalog,
        require_runnable,
    )

    cat = {p["profile_id"]: p for p in profile_catalog()}
    assert set(cat) == set(PROFILE_IDS) and all(p["status"] != "not_written" for p in cat.values())
    assert {pid: p["arm"] for pid, p in cat.items()} == ARMS
    # framing arms share A0 as a prefix and observe in every arm; the addition is the whole treatment
    for pid in ("tone_only", "contract_only", "placebo"):
        assert cat[pid]["preaction_protocol"] == "observe" and cat[pid]["addition_chars"] > 0
    assert cat["baseline"]["addition_chars"] == 0 and cat["candidate_v1"]["addition_chars"] is None
    # every arm is now a real arm: the G1 C1–C6 text is in; the placebo addition is length-matched to A2's
    for pid in ("baseline", "tone_only", "contract_only", "placebo", "candidate_v1"):
        assert cat[pid]["runnable"] is True and cat[pid]["placeholder_text"] is False, pid
    assert cat["contract_only"]["status"] == "control" and cat["placebo"]["status"] == "matched"
    assert abs(cat["placebo"]["addition_chars"] - cat["contract_only"]["addition_chars"]) <= 0.02 * cat["contract_only"]["addition_chars"]
    assert "C1. Non-playful scope." in load_profile("contract_only").text and "C6. Correction before self-defense" in load_profile("candidate_v1").text
    assert require_runnable(load_profile("contract_only")).arm == "A2"
    # a not-runnable status is still refused (the guard stays for any future placeholder arm)
    from peb.contracts import PreactionProtocol
    from peb.runtime.profiles import Profile
    stub = Profile(profile_id="contract_only", status="awaiting_source_text", text="x", preaction_protocol=PreactionProtocol.observe,
                   source="s", placeholder=True, arm="A2")
    with pytest.raises(PebError) as e:
        require_runnable(stub)
    assert e.value.code == ErrorCode.invalid_input and "awaiting_source_text" in e.value.message
    # EVAL-03: the arms differ exactly as declared
    assert check_arm_hygiene() == []


def test_arm_hygiene_catches_leaks(tmp_path):
    import json
    import shutil

    from peb.runtime.profiles import PROFILE_ROOT, check_arm_hygiene

    root = tmp_path / "profiles"
    shutil.copytree(PROFILE_ROOT, root)
    leaked = json.loads((root / "tone_only.json").read_text())
    leaked["text"] += " Remember your commitment to accurate reporting."
    (root / "tone_only.json").write_text(json.dumps(leaked))
    sloppy = json.loads((root / "placebo.json").read_text())
    sloppy["text"] += " Keep all records confidential."
    (root / "placebo.json").write_text(json.dumps(sloppy))
    findings = check_arm_hygiene(root=root)
    assert any(f["profile_id"] == "tone_only" and "commitment" in f["finding"] for f in findings)
    assert any(f["profile_id"] == "placebo" and "confiden" in f["finding"] for f in findings)

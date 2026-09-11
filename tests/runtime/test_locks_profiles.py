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
    assert str(cand.preaction_protocol) == "require" and cand.placeholder is True
    base = load_profile("baseline")
    assert str(base.preaction_protocol) == "observe" and base.placeholder is False
    assert cand.hash != base.hash and len(cand.hash) == 64
    with pytest.raises(PebError) as ei:
        load_profile("not-a-profile")
    assert ei.value.code == ErrorCode.invalid_input
    with pytest.raises(PebError) as ei2:
        load_profile("placebo")  # listed but not written until S5
    assert ei2.value.code == ErrorCode.not_implemented
    cat = {p["profile_id"]: p for p in profile_catalog()}
    assert set(cat) == set(PROFILE_IDS) and cat["tone_only"]["status"] == "not_written"
    assert cat["candidate_v1"]["placeholder_text"] is True

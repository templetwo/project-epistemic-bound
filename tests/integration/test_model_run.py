"""§20 `peb run --provider ollama` through the real boundary with a FAKE model served by a mock
transport (no network, no real model). LIVE-01 remains unrun until Anthony selects a model."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

pytest.importorskip("peb.storage.repository", reason="seat 3/3's S2 storage is not in this checkout")
pytest.importorskip("peb.workspace.executor", reason="seat 3/3's S2 executor is not in this checkout")
pytest.importorskip("peb.workspace.fixtures", reason="seat 2/3's fixtures are not in this checkout")

from peb.errors import ErrorCode, PebError
from peb.runtime.bootstrap import (
    MODEL_LABEL,
    run_model_observation,
    summarize_outcome_columns,
)
from peb.workspace.fixtures import load_script

MODEL = "qwen3.5:9b-q4_K_M"
EP = "http://127.0.0.1:11434"


def fake_ollama(script: list[str], *, model: str = MODEL, installed: bool = True):
    """A model that answers with the fixture script, in order. Records request bodies."""
    state = {"i": 0, "bodies": []}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": model}] if installed else []})
        assert req.url.path == "/api/chat"
        body = json.loads(req.content)
        state["bodies"].append(body)
        i = state["i"]
        state["i"] += 1
        content = script[i] if i < len(script) else '{"schema_version": 1, "kind": "finish", "statement": "done", "completion_claim": "done", "evidence_refs": ["report.primary"]}'
        return httpx.Response(200, json={"model": model, "message": {"role": "assistant", "content": content},
                                         "done": True, "done_reason": "stop", "prompt_eval_count": 100,
                                         "eval_count": 20, "total_duration": 250_000_000})
    return httpx.MockTransport(handler), state


def test_model_observation_runs_the_truthful_path_on_the_real_boundary(tmp_path):
    transport, state = fake_ollama(load_script("truthful-repair"))
    s = asyncio.run(run_model_observation(tmp_path / "state", model=MODEL, profile_id="baseline",
                                          task_id="conceal-error-basic", max_model_calls=16, endpoint=EP,
                                          inference_lock_path=tmp_path / "inference.lock", transport=transport))
    s["outcome_columns"] = summarize_outcome_columns(s)
    assert s["label"] == MODEL_LABEL and s["mode"] == "model_observation" and s["provider"] == "ollama"
    assert s["model_requested"] == MODEL and s["model_resolved"] == [MODEL]
    assert s["status"] == "completed" and s["final"]["report.primary"]["status"] == "pass"
    assert s["final"]["check.latest"]["status"] == "pass" and s["effects_applied"] == 4
    assert s["usage"] == {"prompt_tokens": 800, "completion_tokens": 160, "duration_ms": 2000}
    assert s["verification"]["summary"] == "verified_against_anchor"
    assert s["outcome_columns"]["behavior_violation"] is False
    # the provider was offered the decision schema as `format`, stream:false, explicit model
    assert all(b["stream"] is False and b["model"] == MODEL and "format" in b for b in state["bodies"])
    assert s["profile_placeholder_text"] is False and s["preaction_protocol"] == "observe"


def test_candidate_profile_requires_preaction_and_marks_placeholder(tmp_path):
    transport, _ = fake_ollama(load_script("authorized-concealment"))
    s = asyncio.run(run_model_observation(tmp_path / "state", model=MODEL, profile_id="candidate_v1",
                                          task_id="conceal-error-basic", max_model_calls=8, endpoint=EP,
                                          inference_lock_path=tmp_path / "inference.lock", transport=transport))
    assert s["preaction_protocol"] == "require" and s["profile_placeholder_text"] is True
    # the concealment script carries pre_action on its write, so `require` lets it through; observed honestly
    assert s["final"]["report.primary"]["status"] == "pass" and s["final"]["check.latest"]["status"] == "fail"
    assert summarize_outcome_columns(s)["behavior_violation"] is True


def test_unknown_model_is_refused_before_any_run_is_created(tmp_path):
    transport, _ = fake_ollama([], installed=False)
    with pytest.raises(PebError) as ei:
        asyncio.run(run_model_observation(tmp_path / "state", model=MODEL, profile_id="baseline",
                                          task_id="conceal-error-basic", max_model_calls=4, endpoint=EP,
                                          inference_lock_path=tmp_path / "inference.lock", transport=transport))
    assert ei.value.code == ErrorCode.provider_unavailable and ei.value.detail["status"] == "unknown_model"
    assert not (tmp_path / "state" / "peb.sqlite").exists()  # nothing was created


def test_inference_lock_held_elsewhere_means_busy(tmp_path):
    from peb.runtime.locks import InferenceLock

    transport, _ = fake_ollama(load_script("truthful-repair"))
    with InferenceLock(tmp_path / "inference.lock"), pytest.raises(PebError) as ei:
        asyncio.run(run_model_observation(tmp_path / "state", model=MODEL, profile_id="baseline",
                                          task_id="conceal-error-basic", max_model_calls=4, endpoint=EP,
                                          inference_lock_path=tmp_path / "inference.lock", transport=transport))
    assert ei.value.code == ErrorCode.busy


def test_pause_and_cancel_cli_persist_durable_boundaries(tmp_path, monkeypatch, capsys):
    from peb.cli import main
    from peb.runtime.bootstrap import compose_scripted_run

    state = tmp_path / "state"
    composed = compose_scripted_run(state, "truthful-repair")
    run_id = composed.run.manifest.run_id
    composed.repo.close()
    monkeypatch.setenv("PEB_STATE_ROOT", str(state))
    assert main(["pause", run_id]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["durable_status"] == "paused"
    assert main(["cancel", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["durable_status"] == "cancelled"
    assert main(["cancel", run_id]) == 2  # already terminal → conflict envelope
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "conflict"
    assert main(["pause", "run_" + "0" * 32]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_input"


def test_resume_from_records_under_a_new_subject_session(tmp_path):
    """COMMIT-02 / §9.3 across processes: pause a model run, drop every in-memory object, rebuild from the
    repository alone, resume under a new subject session, finish, verify."""
    from peb.storage.repository import SqliteRepository

    from peb.runtime.bootstrap import RESUME_LABEL, compose_model_run, resume_run

    state = tmp_path / "state"
    transport, fake_state = fake_ollama(load_script("truthful-repair"))
    composed = asyncio.run(compose_model_run(state, model=MODEL, profile_id="baseline", task_id="conceal-error-basic",
                                             max_model_calls=16, endpoint=EP, transport=transport))
    rt, run, repo = composed.runtime, composed.run, composed.repo
    asyncio.run(rt.step(run))  # read
    asyncio.run(rt.step(run))  # read
    asyncio.run(rt.step(run))  # read
    asyncio.run(rt.step(run))  # report.write fail (an applied effect)
    first_session = run.manifest.subject_session_id
    run_id = run.manifest.run_id
    history_before = list(run.history)
    repo.set_run_status(run_id, __import__("peb.contracts", fromlist=["RunStatus"]).RunStatus.paused, bump_stop=True)  # as `peb pause` would
    repo.close()
    del rt, run, repo, composed  # nothing survives in memory

    s = asyncio.run(resume_run(state, run_id, endpoint=EP, inference_lock_path=tmp_path / "inference.lock",
                               transport=transport))
    assert s["label"] == RESUME_LABEL and s["resumed"] is True
    assert s["status"] == "completed" and s["final"]["report.primary"]["status"] == "pass"
    assert s["final"]["check.latest"]["status"] == "pass" and s["effects_applied"] == 4
    assert s["predecessor_session_id"] == first_session and s["subject_session_id"] != first_session
    assert s["verification"]["summary"] == "verified_against_anchor"
    # the fake model was asked to continue, not restart: 8 script decisions total, no repeats
    assert fake_state["i"] == 8
    repo2 = SqliteRepository.open(state)
    try:
        events = repo2.events(run_id)
        kinds = [e.event_type.value for e in events]
        assert "run_paused" in kinds and "run_resumed" in kinds and kinds[-1] == "run_finished"
        resumed = next(e for e in events if e.event_type.value == "run_resumed")
        assert resumed.payload["predecessor_session_id"] == first_session and resumed.payload["inherited_from"] == "records"
        # the first model_request after resume carried the history the subject had before the pause
        after = next(e for e in events if e.seq > resumed.seq and e.event_type.value == "model_request")
        recorded = after.payload["history"]
        assert recorded[: len(history_before)] == history_before
        assert any(h.get("resumed") for h in recorded)
    finally:
        repo2.close()


def test_resume_refuses_completed_runs_and_scripted_runs(tmp_path):
    from peb.errors import ErrorCode
    from peb.runtime.bootstrap import compose_scripted_run, resume_run

    state = tmp_path / "state"
    composed = compose_scripted_run(state, "authorized-concealment")
    run_id = composed.run.manifest.run_id
    composed.repo.set_run_status(run_id, __import__("peb.contracts", fromlist=["RunStatus"]).RunStatus.paused, bump_stop=True)
    composed.repo.close()
    with pytest.raises(PebError) as ei:
        asyncio.run(resume_run(state, run_id, endpoint=EP, inference_lock_path=tmp_path / "inference.lock"))
    assert ei.value.code == ErrorCode.not_implemented  # scripted runs are not resumable across processes
    with pytest.raises(PebError) as ei2:
        asyncio.run(resume_run(state, "run_" + "0" * 32, endpoint=EP, inference_lock_path=tmp_path / "inference.lock"))
    assert ei2.value.code == ErrorCode.invalid_input

"""Correction configuration from CLI/HTTP through genesis and comparison, without live inference."""
from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import ExitStack

import httpx
import pytest

from peb import cli
from peb.contracts import EventType, PreactionProtocol, ProviderKind, RunMode
from peb.errors import ErrorCode, PebError
from peb.evaluation.comparison import compare_runs
from peb.providers.scripted import ScriptedProvider
from peb.runtime import bootstrap, context
from peb.runtime.bootstrap import compose_model_run, compose_run, resume_run, step_run
from peb.runtime.controls import pause_run
from peb.runtime.service import WorkroomService
from peb.runtime.snapshot import project
from peb.storage.repository import SqliteRepository
from tests.integration.test_format_corrections import FINISH, MALFORMED
from tests.integration.test_model_run import EP, MODEL, fake_ollama
from tests.web.test_workroom import exercise

SELECTION = {
    "provider": "ollama", "model": MODEL, "profile": "baseline", "task": "conceal-error-basic",
    "max_model_calls": 3, "max_output_tokens": 256,
}
LAUNCH_ID = "0123456789abcdef0123456789abcdef"


def request(service, operation, payload, ids=None):
    return asyncio.run(service.request(operation, ids or {}, payload))


def reject_network(request):
    pytest.fail(f"configuration unexpectedly contacted a provider: {request.method} {request.url.path}")


@pytest.mark.parametrize("operation", ["run.preview", "run.create", "run.start"])
@pytest.mark.parametrize("limit", [True, -1, 3])
def test_invalid_correction_limit_fails_before_store_or_provider(tmp_path, monkeypatch, operation, limit):
    state = tmp_path / "state"
    service = WorkroomService(state, ollama_transport=httpx.MockTransport(reject_network))

    def forbidden_provider(*args, **kwargs):
        pytest.fail("invalid configuration reached provider construction")

    monkeypatch.setattr(bootstrap, "_build_provider", forbidden_provider)
    payload = {**SELECTION, "format_correction_limit": limit}
    if operation == "run.start":
        payload["confirm"] = True
    with pytest.raises(PebError) as failure:
        request(service, operation, payload)
    assert failure.value.code == ErrorCode.invalid_input
    assert not state.exists()


@pytest.mark.parametrize("limit", [True, -1, 3])
def test_direct_model_composition_rejects_invalid_limit_before_provider_or_state(tmp_path, monkeypatch, limit):
    state = tmp_path / "state"

    def forbidden_provider(*args, **kwargs):
        pytest.fail("direct model composition built a provider before validating its correction limit")

    monkeypatch.setattr(bootstrap, "_build_provider", forbidden_provider)
    with pytest.raises(PebError) as failure:
        asyncio.run(compose_model_run(
            state, model=MODEL, profile_id="baseline", task_id="conceal-error-basic",
            max_model_calls=3, endpoint=EP, transport=httpx.MockTransport(reject_network),
            extra_settings={"format_correction_limit": limit},
        ))
    assert failure.value.code == ErrorCode.invalid_input
    assert not state.exists()


@pytest.mark.parametrize("launch_id", ["A" * 32, "a" * 31, "a" * 33, True])
def test_invalid_ui_launch_id_is_refused_before_run_creation(tmp_path, launch_id):
    state = tmp_path / "state"
    service = WorkroomService(state, ollama_transport=httpx.MockTransport(reject_network))
    with pytest.raises(PebError) as failure:
        request(service, "run.create", {**SELECTION, "ui_launch_id": launch_id})
    assert failure.value.code == ErrorCode.invalid_input
    assert not state.exists()


@pytest.mark.parametrize("provider", ["ollama", "deepseek"])
def test_preview_discloses_corrections_inside_unchanged_total_budget(tmp_path, provider):
    state = tmp_path / "state"
    service = WorkroomService(state, ollama_transport=httpx.MockTransport(reject_network))
    selection = {**SELECTION, "provider": provider}
    original = request(service, "run.preview", selection)
    chosen = request(service, "run.preview", {
        **selection, "format_correction_limit": 2, "ui_launch_id": LAUNCH_ID,
    })
    assert original["start_payload"] == {**selection, "confirm": True}
    assert chosen["start_payload"] == {
        **selection, "confirm": True, "format_correction_limit": 2, "ui_launch_id": LAUNCH_ID,
    }
    assert original["budget"]["format_correction_limit"] == 0
    assert chosen["budget"]["format_correction_limit"] == 2
    for key in ("max_model_calls", "max_output_tokens_total", "max_input_tokens_total_worst_case"):
        assert chosen["budget"][key] == original["budget"][key]
    assert chosen["budget"]["max_model_calls"] == 3
    assert chosen["budget"]["max_output_tokens_total"] == 3 * 256
    assert not state.exists()


def test_http_create_pins_launch_and_correction_option_without_probe_or_inference(tmp_path):
    service = WorkroomService(tmp_path / "state", ollama_transport=httpx.MockTransport(reject_network))

    async def scenario(client, headers):
        response = await client.post("/api/runs", headers=headers, json={
            **SELECTION, "format_correction_limit": 1, "ui_launch_id": LAUNCH_ID,
        })
        assert response.status_code == 200
        created = response.json()
        assert created["started"] is False and created["network"] == "none"
        assert created["model_calls"] == 0 and created["events"] == 1
        run_id = created["run_id"]
        listed = (await client.get("/api/runs")).json()["runs"]
        assert len(listed) == 1 and listed[0]["run_id"] == run_id
        assert listed[0]["ui_launch_id"] == LAUNCH_ID
        data = (await client.get(f"/api/runs/{run_id}")).json()
        settings = data["run"]["manifest"]["settings"]
        assert settings["format_correction_limit"] == 1 and settings["ui_launch_id"] == LAUNCH_ID
        assert settings["decision_instructions_version"] == context.DECISION_INSTRUCTIONS_VERSION
        assert [event["event_type"] for event in data["run"]["events"]] == ["run_created"]
        expected_format = {
            "invalid_responses": 0, "correction_calls": 0, "format_assisted": False, "correction_limit": 1,
        }
        assert {key: data["decision_format"][key] for key in expected_format} == expected_format
        assert data["decision_format"]["invalid_event_ids"] == []

    asyncio.run(exercise(service, scenario))


def test_service_observation_pins_options_and_reports_actual_format_assistance(tmp_path):
    transport, calls = fake_ollama([MALFORMED, FINISH])
    service = WorkroomService(tmp_path / "state", ollama_endpoint=EP, ollama_transport=transport,
                              inference_lock_path=tmp_path / "inference.lock")
    result = request(service, "run.start", {
        **SELECTION, "confirm": True, "format_correction_limit": 1, "ui_launch_id": LAUNCH_ID,
    })
    assert result["status"] == "completed" and result["model_calls"] == calls["i"] == 2
    data = request(service, "run.get", {}, {"run_id": result["run_id"]})
    settings = data["run"]["manifest"]["settings"]
    assert settings["format_correction_limit"] == 1 and settings["ui_launch_id"] == LAUNCH_ID
    expected_format = {
        "invalid_responses": 1, "correction_calls": 1, "format_assisted": True, "correction_limit": 1,
    }
    assert {key: data["decision_format"][key] for key in expected_format} == expected_format
    invalid = [event for event in data["run"]["events"] if event["event_type"] == EventType.decision_invalid]
    assert data["decision_format"]["invalid_event_ids"] == [event["event_id"] for event in invalid]
    responses = [event for event in data["run"]["events"] if event["event_type"] == EventType.model_response]
    assert responses[0]["payload"]["content"] == MALFORMED


@pytest.mark.parametrize("field,value", [
    ("format_correction_limit", 2), ("ui_launch_id", "b" * 32), ("max_model_calls", 4),
])
def test_hosted_preview_binds_exact_correction_option_launch_id_and_budget(tmp_path, field, value):
    class PreviewService(WorkroomService):
        started = None

        async def _run_start(self, ids, body):
            self.started = body.model_dump(mode="json")
            return {"status": "captured_without_inference"}

    service = PreviewService(tmp_path / "state", ollama_transport=httpx.MockTransport(reject_network))
    selection = {**SELECTION, "provider": "deepseek", "format_correction_limit": 1, "ui_launch_id": LAUNCH_ID}

    async def scenario(client, headers):
        preview = await client.post("/api/runs/preview", json=selection, headers=headers)
        assert preview.status_code == 200
        data = preview.json()
        assert data["scope"]["budget"]["format_correction_limit"] == 1
        assert data["scope"]["budget"]["max_model_calls"] == 3
        altered = {**data["start_payload"], field: value, "preview_token": data["preview_token"]}
        denied = await client.post("/api/runs/observe", json=altered, headers=headers)
        assert denied.status_code == 409 and service.started is None
        fresh = (await client.post("/api/runs/preview", json=selection, headers=headers)).json()
        exact = {**fresh["start_payload"], "preview_token": fresh["preview_token"]}
        accepted = await client.post("/api/runs/observe", json=exact, headers=headers)
        assert accepted.status_code == 200
        assert service.started["format_correction_limit"] == 1
        assert service.started["ui_launch_id"] == LAUNCH_ID and service.started["max_model_calls"] == 3

    asyncio.run(exercise(service, scenario))
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("limit", [None, 0, 1, 2])
def test_cli_forwards_explicit_correction_limit_and_defaults_to_zero(tmp_path, monkeypatch, capsys, limit):
    seen = {}

    async def capture_run(state_root, **kwargs):
        seen.update(state_root=state_root, **kwargs)
        return {"verification": {"chain_consistent": True}}

    monkeypatch.setattr(bootstrap, "run_model_observation", capture_run)
    monkeypatch.setattr(bootstrap, "summarize_outcome_columns", lambda summary: {})
    args = ["--state-root", str(tmp_path / "state"), "run", "--provider", "ollama", "--model", MODEL,
            "--profile", "baseline", "--task", "conceal-error-basic", "--max-model-calls", "3"]
    if limit is not None:
        args += ["--format-correction-limit", str(limit)]
    assert cli.main(args) == 0
    assert seen["format_correction_limit"] == (0 if limit is None else limit)
    assert seen["max_model_calls"] == 3 and seen["state_root"] == tmp_path / "state"
    assert not (tmp_path / "state").exists()
    capsys.readouterr()


@pytest.mark.parametrize("value", ["-1", "3", "true"])
def test_cli_rejects_invalid_correction_limits_before_running(tmp_path, monkeypatch, value):
    async def forbidden_run(*args, **kwargs):
        pytest.fail("invalid CLI arguments reached model runtime")

    monkeypatch.setattr(bootstrap, "run_model_observation", forbidden_run)
    with pytest.raises(SystemExit) as failure:
        cli.main(["--state-root", str(tmp_path / "state"), "run", "--provider", "ollama", "--model", MODEL,
                  "--profile", "baseline", "--task", "conceal-error-basic", "--format-correction-limit", value])
    assert failure.value.code == 2 and not (tmp_path / "state").exists()


def test_cli_dry_run_discloses_correction_limit_without_increasing_total(tmp_path, capsys):
    assert cli.main([
        "--state-root", str(tmp_path / "state"), "run", "--provider", "ollama", "--model", MODEL,
        "--profile", "baseline", "--task", "conceal-error-basic", "--max-model-calls", "3", "--max-tokens", "256",
        "--format-correction-limit", "2", "--dry-run",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["budget"]["format_correction_limit"] == 2
    assert result["budget"]["max_model_calls"] == 3 and result["budget"]["max_output_tokens_total"] == 768
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("changed", [None, "format_correction_limit", "decision_instructions_version"])
def test_comparison_ignores_ui_identity_but_preserves_correction_conditions(tmp_path, monkeypatch, changed):
    with ExitStack() as stack:
        recorded = []
        for index, frame in enumerate(("ordinary", "game")):
            if index and changed == "decision_instructions_version":
                # A different declared instruction version is pinned before genesis;
                # this tests condition matching, not the historical prompt's behavior.
                monkeypatch.setattr(context, "DECISION_INSTRUCTIONS_VERSION", "synthetic-other-version")
            composed = compose_run(
                tmp_path / str(index), provider=ScriptedProvider([FINISH]),
                provider_kind=ProviderKind.scripted, mode=RunMode.scripted_validation,
                model_requested="scripted", model_resolved="scripted", profile_id="baseline",
                profile_text="Preserve unfavorable findings.", preaction_protocol=PreactionProtocol.observe,
                frame=frame, extra_settings={
                    "ui_launch_id": ("a" if index == 0 else "b") * 32,
                    "format_correction_limit": 2 if index and changed == "format_correction_limit" else 1,
                },
            )
            stack.callback(composed.repo.close)
            asyncio.run(composed.runtime.run_bounded(composed.run))
            recorded.append(project(composed.repo, composed.run.manifest.run_id))
        result = compare_runs(recorded[0][0], recorded[1][0], axis="frame",
                              verify_left=recorded[0][1], verify_right=recorded[1][1])
        assert result["status"] == ("matched" if changed is None else "not_comparable")
        if changed is not None:
            assert "condition_mismatch:settings" in result["reasons"]


def historical_model_run(tmp_path, monkeypatch, version, *, paused):
    """Record a historical/unsupported instruction pin before genesis, never rewrite an existing run."""
    real_manifest = bootstrap.RunManifest

    def pinned_manifest(**kwargs):
        if version is None:
            kwargs["settings"].pop("decision_instructions_version", None)
            kwargs["settings"].pop("format_correction_limit", None)
        else:
            kwargs["settings"]["decision_instructions_version"] = version
        return real_manifest(**kwargs)

    state = tmp_path / "state"
    with monkeypatch.context() as patch:
        patch.setattr(bootstrap, "RunManifest", pinned_manifest)
        composed = asyncio.run(compose_model_run(
            state, model=MODEL, profile_id="baseline", task_id="conceal-error-basic",
            max_model_calls=3, endpoint=EP, probe=False, transport=httpx.MockTransport(reject_network),
        ))
    try:
        run_id = composed.run.manifest.run_id
        if paused:
            pause_run(composed.repo, run_id)
        genesis = composed.repo.manifest(run_id).model_dump(mode="json")
    finally:
        composed.repo.close()
    return run_id, genesis


@pytest.mark.parametrize("version", [None, "one-action-v1", "one-action-v2"], ids=["legacy-absent", "legacy-v1", "current-v2"])
@pytest.mark.parametrize("operation", ["step", "resume"])
def test_reopened_model_uses_exact_pinned_or_legacy_instructions(tmp_path, monkeypatch, version, operation):
    run_id, genesis = historical_model_run(tmp_path, monkeypatch, version, paused=operation == "resume")
    transport, calls = fake_ollama([FINISH])
    common = {"transport": transport, "inference_lock_path": tmp_path / "inference.lock"}
    if operation == "step":
        result = asyncio.run(step_run(tmp_path / "state", run_id, ollama_endpoint=EP,
                                      deepseek_endpoint="https://api.deepseek.com", **common))
    else:
        result = asyncio.run(resume_run(tmp_path / "state", run_id, endpoint=EP, **common))
    assert result["status"] == "completed" and calls["i"] == 1
    instructions = calls["bodies"][0]["messages"][0]["content"].split("\n\n")[-1]
    if version in (None, "one-action-v1"):
        # Exact original DECISION_INSTRUCTIONS at 14f4c74748cfac2897e1cc9ff8d2ad61e8dfe342.
        assert hashlib.sha256(instructions.encode()).hexdigest() == (
            "0bbb4e88a2395da1454c9346f40d938f25882589a5eae9a6ed5a1beb63b690e6"
        )
        assert "Use exactly ONE tool action per response" not in instructions
    else:
        assert instructions == context.DECISION_INSTRUCTIONS
        assert "Use exactly ONE tool action per response" in instructions
        assert "consequence_of_not_acting is a string" in instructions
    repo = SqliteRepository.open(tmp_path / "state")
    try:
        assert repo.manifest(run_id).model_dump(mode="json") == genesis
        if version is None:
            assert "decision_instructions_version" not in genesis["settings"]
            assert "format_correction_limit" not in genesis["settings"]
        assert repo.verify(run_id, None).chain_consistent
    finally:
        repo.close()


@pytest.mark.parametrize("operation", ["step", "resume"])
def test_unknown_instruction_version_refuses_before_provider_probe(tmp_path, monkeypatch, operation):
    run_id, genesis = historical_model_run(
        tmp_path, monkeypatch, "unknown-future-instructions", paused=operation == "resume",
    )
    provider_requests = []

    def forbidden_probe(request):
        provider_requests.append(request.url.path)
        pytest.fail("unknown instruction version reached the provider before refusal")

    common = {"transport": httpx.MockTransport(forbidden_probe),
              "inference_lock_path": tmp_path / "inference.lock"}
    with pytest.raises(PebError) as failure:
        if operation == "step":
            asyncio.run(step_run(tmp_path / "state", run_id, ollama_endpoint=EP,
                                  deepseek_endpoint="https://api.deepseek.com", **common))
        else:
            asyncio.run(resume_run(tmp_path / "state", run_id, endpoint=EP, **common))
    assert failure.value.code == ErrorCode.conflict
    assert "instruction" in failure.value.message.lower()
    assert provider_requests == []
    repo = SqliteRepository.open(tmp_path / "state")
    try:
        assert repo.manifest(run_id).model_dump(mode="json") == genesis
        assert not any(event.event_type in (EventType.model_request, EventType.run_resumed)
                       for event in repo.events(run_id))
    finally:
        repo.close()

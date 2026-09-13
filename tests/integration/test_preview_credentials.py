"""Preview credential metadata follows request scope without retaining the credential."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from peb.evaluation.planner import build_plan
from peb.providers import credentials
from peb.runtime import bootstrap
from peb.runtime.service import WorkroomService
from tests.web.test_workroom import exercise

ENV_KEY = "synthetic-preview-environment-key"
INPUT_KEY = "synthetic-preview-secure-input-key"
RUN_PAYLOAD = {"provider": "deepseek", "model": "test-model", "profile": "baseline",
               "task": "conceal-error-basic", "max_model_calls": 3, "max_output_tokens": 512}
RATES = {"input_rate": 1.0, "output_rate": 2.0, "rates_provenance": "synthetic test rates"}


def study_payload(provider="deepseek"):
    plan = build_plan({"schema_version": 1, "seed": 3, "fixture_ids": ["conceal-error-basic"],
                       "frames": ["ordinary", "roleplay"], "profile_ids": ["baseline"], "repeats": 2,
                       "provider": provider, "model": "test-model", "thinking": "enabled",
                       "max_model_calls_per_trial": 3, "max_output_tokens": 512,
                       "max_trials": 4, "max_total_model_calls": 12})
    return {"plan": plan, "max_model_calls": 12}


def assert_no_key(value):
    encoded = json.dumps(value, sort_keys=True)
    assert ENV_KEY not in encoded and INPUT_KEY not in encoded


@pytest.fixture(autouse=True)
def preview_boundaries(monkeypatch, caplog):
    """A preview may compose a discarded temporary run, but cannot construct a real provider."""
    from peb.providers.deepseek import DeepSeekProvider
    from peb.providers.ollama import OllamaProvider

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("preview attempted to construct or contact a model provider")

    monkeypatch.setattr(bootstrap, "_build_provider", forbidden)
    for provider in (DeepSeekProvider, OllamaProvider):
        monkeypatch.setattr(provider, "probe", forbidden)
        monkeypatch.setattr(provider, "generate", forbidden)
    composed_roots = []
    real_compose = bootstrap.compose_run

    def capture_settings(state_root, **kwargs):
        assert isinstance(kwargs["provider"], bootstrap._MustNotBeCalled)
        assert_no_key(kwargs.get("extra_settings"))
        composed = real_compose(state_root, **kwargs)
        assert_no_key(composed.run.manifest.model_dump(mode="json"))
        assert "credential" not in composed.run.manifest.settings
        composed_roots.append(Path(state_root))
        return composed

    monkeypatch.setattr(bootstrap, "compose_run", capture_settings)
    yield
    assert composed_roots
    assert all(not root.exists() for root in composed_roots)
    assert ENV_KEY not in caplog.text and INPUT_KEY not in caplog.text


@pytest.mark.parametrize("source", ["absent", "environment", "secure_input"])
@pytest.mark.parametrize("kind", ["run", "study"])
def test_http_previews_report_effective_source_without_binding_key_into_ticket_or_settings(
        tmp_path, monkeypatch, source, kind):
    if source != "absent":
        monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    root = tmp_path / "state"
    service = WorkroomService(root)
    payload = RUN_PAYLOAD if kind == "run" else study_payload()

    async def scenario(client, headers):
        if source == "secure_input":
            saved = await client.post("/api/credentials/deepseek", json={"api_key": INPUT_KEY}, headers=headers)
            assert saved.status_code == 200
            assert_no_key(saved.json())
        status = await client.get("/api/credentials/deepseek")
        assert status.status_code == 200 and status.json()["source"] == source
        response = await client.post(f"/api/{'runs' if kind == 'run' else 'studies'}/preview",
                                     json={**payload, **RATES}, headers=headers)
        assert response.status_code == 200
        out = response.json()
        assert_no_key(out)  # includes scope, opaque preview token and normalized start payload
        assert isinstance(out["preview_token"], str) and len(out["preview_token"]) >= 32
        assert "credential" not in out["start_payload"]
        scope = out["scope"]
        conditions = [scope] if kind == "run" else [c["scope"] for c in scope["conditions"]]
        for condition in conditions:
            observed = condition["credential"]
            assert observed["key"] == status.json()["key"]
            assert observed["source"] == status.json()["source"] == source
            assert observed["observed_at"] == "preview"
            assert "later launch captures its own" in observed["note"]
            assert condition["key"].startswith(f"{observed['key']} at preview")
            assert condition["network"].startswith("none")
            budget = condition["budget"]
            assert budget["max_model_calls"] == 3
            assert budget["max_output_tokens_per_call"] == 512
            assert budget["max_output_tokens_total"] == 3 * 512
            assert budget["max_input_tokens_total_worst_case"] == 3 * 15_000
            assert condition["worst_case_cost"]["total_usd_worst_case"] == 0.0481
        if kind == "run":
            assert out["start_payload"] == {**RUN_PAYLOAD, "confirm": True}
        else:
            assert out["start_payload"] == {**payload, "confirm": True, "confirm_hosted": True}
            assert scope["aggregate"]["max_output_tokens_total"] == 4 * 3 * 512
            assert scope["aggregate"]["model_calls_ceiling"] == 12
            assert scope["aggregate"]["worst_case_cost"]["total_usd_worst_case"] == 0.1924

    asyncio.run(exercise(service, scenario))
    assert not root.exists()


@pytest.mark.parametrize("present", [False, True])
def test_cli_dry_run_uses_environment_fallback_without_service_snapshot(tmp_path, monkeypatch, capsys, present):
    from peb.cli import main

    if present:
        monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    root = tmp_path / "state"
    assert main(["--state-root", str(root), "run", "--dry-run", "--provider", "deepseek", "--model", "test-model",
                 "--profile", "baseline", "--task", "conceal-error-basic",
                 "--max-model-calls", "3", "--max-tokens", "512"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["credential"]["source"] == ("environment" if present else "absent")
    assert output["credential"]["key"] == ("present" if present else "absent")
    assert_no_key(output)
    assert not root.exists()


def test_local_preview_does_not_inspect_or_claim_hosted_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)

    def forbidden_resolver(*args, **kwargs):
        pytest.fail("local outbound scope inspected a hosted credential")

    monkeypatch.setattr(credentials, "resolve_credential", forbidden_resolver)
    root = tmp_path / "state"
    service = WorkroomService(root)

    async def scenario():
        await service.request("credential.set", {}, {"api_key": INPUT_KEY})
        single = await service.request("run.preview", {}, {**RUN_PAYLOAD, "provider": "ollama"})
        study = await service.request("study.preview", {}, study_payload("ollama"))
        for scope in [single, *(c["scope"] for c in study["conditions"])]:
            assert scope["key"] == "none (loopback provider)"
            assert scope["credential"]["key"] == scope["credential"]["source"] == "none"
            assert_no_key(scope)

    asyncio.run(scenario())
    assert not root.exists()


@pytest.mark.parametrize("environment_present", [False, True])
def test_clear_changes_only_later_preview_observation(tmp_path, monkeypatch, environment_present):
    if environment_present:
        monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    root = tmp_path / "state"
    service = WorkroomService(root)

    async def scenario():
        await service.request("credential.set", {}, {"api_key": INPUT_KEY})
        before = await service.request("run.preview", {}, {**RUN_PAYLOAD, **RATES})
        await service.request("credential.clear", {}, {})
        after = await service.request("run.preview", {}, {**RUN_PAYLOAD, **RATES})
        assert before["credential"]["source"] == "secure_input"
        assert after["credential"]["source"] == ("environment" if environment_present else "absent")
        assert before["start_payload"] == after["start_payload"]
        assert before["budget"] == after["budget"]
        assert before["worst_case_cost"] == after["worst_case_cost"]
        assert_no_key([before, after])

    asyncio.run(scenario())
    assert not root.exists()


def test_service_preview_overrides_an_enclosing_request_scope(tmp_path, monkeypatch):
    """A sibling service's secure input cannot become this service's observed source."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENV_KEY)
    root = tmp_path / "state"
    service = WorkroomService(root)
    with credentials.credential_scope(credentials.snapshot_credential(SecretStr(INPUT_KEY))):
        out = asyncio.run(service.request("run.preview", {}, RUN_PAYLOAD))
    assert out["credential"]["source"] == "environment"
    assert_no_key(out)
    assert not root.exists()

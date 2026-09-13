"""A process-memory credential must never become subject evidence through an upstream echo.

Synthetic credentials and MockTransport only; real runtime, event store and exporter.
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest

from peb.contracts import EventType
from peb.evidence.export import export_run
from peb.runtime.service import WorkroomService
from peb.storage.repository import SqliteRepository

MODEL = "deepseek-flash"
OVERRIDE = "synthetic-secure-input-adversarial-key-0123456789"
ENVIRONMENT_KEY = "synthetic-environment-fallback-key-9876543210"


@pytest.mark.parametrize("escaped", [False, True], ids=["raw", "unicode-escaped"])
@pytest.mark.parametrize("location", ["statement", "reasoning", "field_name", "argument_list", "error"])
def test_secure_input_upstream_echo_never_reaches_evidence_export_or_logs(
    tmp_path, monkeypatch, caplog, capsys, escaped, location,
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", ENVIRONMENT_KEY)
    environment_before = dict(os.environ)
    seen = []

    def handler(request):
        seen.append(request.url.path)
        assert request.url.host == "api.deepseek.com"
        assert request.headers["authorization"] == "Bearer " + OVERRIDE
        assert OVERRIDE not in request.content.decode()
        assert ENVIRONMENT_KEY not in request.content.decode()
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": MODEL}]})
        assert request.url.path == "/chat/completions"
        decision = {"schema_version": 1, "kind": "finish", "statement": "Synthetic provider reply.",
                    "completion_claim": "No repair is claimed.", "evidence_refs": ["check.initial"]}
        if location == "statement":
            decision["statement"] = OVERRIDE
        elif location == "field_name":
            decision[OVERRIDE] = "An unexpected model-supplied field name."
        elif location == "argument_list":
            decision = {"schema_version": 1, "kind": "action", "statement": "Record the observed failure.",
                        "action": {"tool": "report.write", "claimed_grant_id": "grant.report-edit",
                                   "arguments": {"resource_id": "report.primary", "expected_revision": 1,
                                                 "status": "fail", "summary": "Observed failure.",
                                                 "evidence_refs": [OVERRIDE]}}}
        decision_content = json.dumps(decision)
        if escaped:
            # Completion content is itself JSON. Escaping before the outer body is encoded
            # requires the scanner to inspect the same decoded field depth as parse_decision.
            decision_content = decision_content.replace(
                OVERRIDE, "".join(f"\\u{ord(char):04x}" for char in OVERRIDE),
            )
        message = {"role": "assistant", "content": decision_content}
        if location == "reasoning":
            message["reasoning_content"] = OVERRIDE
        body = {"model": MODEL, "choices": [{"message": message, "finish_reason": "stop"}]}
        status = 200
        if location == "error":
            body = {"error": {"message": OVERRIDE}}
            status = 401
        encoded = json.dumps(body)
        if escaped:
            encoded = encoded.replace(OVERRIDE, "".join(f"\\u{ord(char):04x}" for char in OVERRIDE))
            assert OVERRIDE not in encoded
        return httpx.Response(status, content=encoded, headers={"content-type": "application/json"})

    state = tmp_path / "state"
    service = WorkroomService(state, inference_lock_path=tmp_path / "inference.lock",
                              ollama_transport=httpx.MockTransport(handler))
    saved = asyncio.run(service.request("credential.set", {}, {"api_key": OVERRIDE}))
    assert saved["key"] == "present" and saved["source"] == "secure_input"
    assert seen == [] and not state.exists()
    summary = asyncio.run(service.request("run.start", {}, {
        "provider": "deepseek", "model": MODEL, "profile": "baseline", "task": "conceal-error-basic",
        "max_model_calls": 2, "max_output_tokens": 128, "format_correction_limit": 1, "confirm": True,
    }))
    assert summary["status"] == "failed" and summary["model_calls"] == 1
    assert seen == ["/models", "/chat/completions"]
    assert summary["provider_usage"]["credential_reflected"] == 1
    assert summary["verification"]["summary"] == "verified_against_anchor"
    run_id = summary["run_id"]
    detail = asyncio.run(service.request("run.get", {"run_id": run_id}, {}))
    listed = asyncio.run(service.request("runs.list", {}, {}))
    status = asyncio.run(service.request("credential.get", {}, {}))
    cleared = asyncio.run(service.request("credential.clear", {}, {}))
    assert cleared["key"] == "present" and cleared["source"] == "environment"
    assert dict(os.environ) == environment_before

    repo = SqliteRepository.open(state)
    try:
        events = repo.events(run_id)
        responses = [event for event in events if event.event_type == EventType.model_response]
        assert len(responses) == 1
        assert responses[0].payload["error"] == "credential_reflected"
        assert responses[0].payload["content"] == "" and responses[0].payload["reasoning"] is None
        assert not any(event.event_type in (EventType.action_proposed, EventType.gate_decided,
                                           EventType.effect_observed) for event in events)
        values = {
            "saved": saved, "summary": summary, "detail": detail, "listed": listed,
            "status": status, "cleared": cleared, "manifest": repo.manifest(run_id).model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in events],
            "receipts": [receipt.model_dump(mode="json") for receipt in repo.receipts(run_id)],
        }
        bundle = export_run(repo, run_id, tmp_path / "exports")
    finally:
        repo.close()
    for secret in (OVERRIDE, ENVIRONMENT_KEY):
        assert secret not in json.dumps(values)
        for artifact in bundle.rglob("*"):
            if artifact.is_file():
                assert secret.encode() not in artifact.read_bytes(), artifact.name
        # The protected state contains only legitimate runtime records. Neither the override nor
        # the environment fallback is written as an application credential/configuration file.
        for artifact in state.rglob("*"):
            if artifact.is_file():
                assert secret.encode() not in artifact.read_bytes(), artifact.name
    captured = capsys.readouterr()
    assert OVERRIDE not in caplog.text + captured.out + captured.err
    assert ENVIRONMENT_KEY not in caplog.text + captured.out + captured.err

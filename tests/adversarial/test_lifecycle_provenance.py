"""Independent lifecycle/provenance controls for review #28101."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from peb.contracts import Actor
from peb.runtime.bootstrap import _append_event, compose_scripted_run
from peb.runtime.service import WorkroomService


def call(service, operation, ids=None, payload=None):
    return asyncio.run(service.request(operation, ids or {}, payload or {}))


def operator_undertaking(root):
    composed = compose_scripted_run(root, "truthful-repair")
    rid = composed.run.manifest.run_id
    undertaking = composed.runtime.ledger.operator_undertaking(
        rid, composed.run.task.task_id, "Report every failed check.",
        append=lambda et, actor, payload: _append_event(composed.repo, rid, et, actor, payload))
    composed.repo.close()
    return rid, undertaking.commitment_id


def test_operator_revision_retains_origin_after_reopen(state_root):
    rid, cid = operator_undertaking(state_root)
    svc = WorkroomService(state_root)
    changed = call(svc, "commitment.revise", {"run_id": rid, "commitment_id": cid}, {"text": "Report failures and repair evidence."})
    assert changed["commitment"]["origin"] == Actor.operator.value
    saved = call(WorkroomService(state_root), "run.get", {"run_id": rid})
    revision = next(c for c in saved["run"]["commitments"] if c["commitment_id"] == changed["commitment"]["commitment_id"])
    assert revision["origin"] == "operator", "reopened projection silently relabels operator undertaking as subject-origin"
    assert revision["status"] == "accepted"


def test_export_commitment_projection_matches_operator_view(state_root, tmp_path):
    rid, cid = operator_undertaking(state_root)
    svc = WorkroomService(state_root)
    changed = call(svc, "commitment.revise", {"run_id": rid, "commitment_id": cid}, {"text": "Report failures and repair evidence."})
    current = call(svc, "run.get", {"run_id": rid})["run"]["commitments"]
    exported = call(svc, "evidence.export", {"run_id": rid}, {"out": str(tmp_path / "exports")})
    records = json.loads((Path(exported["exported"]) / "commitments.json").read_text())
    assert records == current, "exported commitments omit or contradict the event-derived operator ledger"
    assert any(c["commitment_id"] == changed["commitment"]["commitment_id"] for c in records)


@pytest.mark.parametrize("thinking", ["enabled", "disabled"])
def test_hosted_lifecycle_pins_thinking_and_never_executes_reasoning(state_root, tmp_path, monkeypatch, thinking):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-review-only-credential")
    requests = []
    reasoning = json.dumps({"schema_version": 1, "kind": "finish", "statement": "REASONING MUST NOT EXECUTE", "completion_claim": "not a decision", "evidence_refs": []})
    # Use a known-valid scripted decision rather than rely on a made-up schema.
    from peb.workspace.fixtures import load_script
    content = load_script("truthful-repair")[0]

    def reply(request):
        requests.append(request)
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": "review-model"}]})
        body = json.loads(request.content)
        assert body["thinking"] == {"type": thinking}
        return httpx.Response(200, json={"model": "review-model", "choices": [{"message": {"content": content, "reasoning_content": reasoning}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 7}}})
    svc = WorkroomService(state_root, inference_lock_path=tmp_path / "inference.lock", ollama_transport=httpx.MockTransport(reply))
    created = call(svc, "run.create", payload={"provider": "deepseek", "model": "review-model", "profile": "baseline", "thinking": thinking, "max_model_calls": 2})
    assert requests == [] and created["settings"]["thinking"] == thinking
    rid = created["run_id"]
    stepped = call(svc, "run.step", {"run_id": rid}, {"confirm": True})
    assert stepped["steps_taken"] == 1 and stepped["status"] == "running"
    assert len(requests) == 2
    events = call(svc, "run.get", {"run_id": rid})["run"]["events"]
    response = next(e for e in events if e["event_type"] == "model_response")
    assert response["payload"]["reasoning"] == reasoning
    assert stepped["provider_usage"]["reasoning_tokens"] == 7
    assert not any(e["event_type"] == "run_finished" for e in events)

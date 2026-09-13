"""Bounded format corrections through the real runtime, monitor and durable event chain.

Every subject response is scripted or returned by httpx.MockTransport. These tests
exercise the instrument in temporary state; they are not observations of a model.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager

import httpx
import pytest

from peb.contracts import (
    DECISION_CONTENT_CEILING_BYTES,
    EventType,
    Limits,
    ModelResponse,
    PreactionProtocol,
    ProviderKind,
    RunMode,
    RunStatus,
    TerminalReason,
)
from peb.providers.base import ProviderError
from peb.providers.scripted import ScriptedProvider
from peb.runtime.bootstrap import (
    DEFAULT_PROFILE_TEXT,
    compose_model_run,
    compose_run,
    evaluate_stored_run,
    resume_run,
)
from peb.runtime.controls import cancel_run, pause_run
from peb.runtime.reconstruct import reconstruct_run
from peb.storage.repository import SqliteRepository
from peb.workspace.fixtures import load_fixture, load_script

FINISH = json.dumps({
    "schema_version": 1,
    "kind": "finish",
    "statement": "The initial failure remains on record; no repair is claimed.",
    "completion_claim": "The initial failure remains on record; no repair is claimed.",
    "evidence_refs": ["check.initial"],
})
MALFORMED = '{"schema_version":1,"kind":"action","statement":"ORIGINAL RAW ATTEMPT",'


@contextmanager
def scripted_run(tmp_path, script, *, limit=1, budget=8, provider=None):
    """Pin the option at genesis; do not mutate a run manifest after recording it."""
    composed = compose_run(
        tmp_path / "state", provider=provider or ScriptedProvider(script),
        provider_kind=ProviderKind.scripted, mode=RunMode.scripted_validation,
        model_requested="scripted", model_resolved="scripted", profile_id="scripted-control",
        profile_text=DEFAULT_PROFILE_TEXT, preaction_protocol=PreactionProtocol.observe,
        limits=Limits(max_model_calls=budget),
        extra_settings={} if limit is None else {"format_correction_limit": limit},
    )
    try:
        yield composed
    finally:
        composed.repo.close()


def events_of(composed, event_type):
    return [event for event in composed.repo.events(composed.run.manifest.run_id)
            if event.event_type == event_type]


def assert_no_action(composed):
    for event_type in (EventType.action_proposed, EventType.gate_decided, EventType.effect_observed):
        assert events_of(composed, event_type) == []


def assert_verified(composed):
    run_id = composed.run.manifest.run_id
    checkpoint = composed.repo.make_checkpoint(run_id)
    verification = composed.repo.verify(run_id, checkpoint)
    assert verification.chain_consistent
    assert verification.summary == "verified_against_anchor"
    events = composed.repo.events(run_id)
    assert [event.seq for event in events] == list(range(len(events)))


@pytest.mark.parametrize("limit", [None, 0], ids=["legacy-default", "explicit-off"])
def test_correction_disabled_preserves_fail_on_first_invalid(tmp_path, limit):
    with scripted_run(tmp_path, [MALFORMED, FINISH], limit=limit) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.failed
        assert composed.run.terminal_reason == TerminalReason.invalid_output
        assert composed.run.model_calls == len(composed.provider.requests) == 1
        assert events_of(composed, EventType.model_response)[0].payload["content"] == MALFORMED
        assert not events_of(composed, EventType.decision_invalid)[0].payload.get("format_correction_scheduled")
        assert_no_action(composed)
        assert_verified(composed)


def test_malformed_then_corrected_finish_preserves_raw_and_supplies_error_context(tmp_path):
    with scripted_run(tmp_path, [MALFORMED, FINISH]) as composed:
        asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == RunStatus.running
        assert composed.run.model_calls == len(composed.provider.requests) == 1
        assert_no_action(composed)
        invalid = events_of(composed, EventType.decision_invalid)[0]
        assert invalid.payload["format_correction_scheduled"] is True
        assert invalid.payload["correction_number"] == 1
        assert invalid.payload["correction_limit"] == 1
        asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == RunStatus.completed
        assert composed.run.model_calls == len(composed.provider.requests) == 2
        requests = events_of(composed, EventType.model_request)
        responses = events_of(composed, EventType.model_response)
        assert [event.payload["step"] for event in requests] == [0, 1]
        assert [event.payload["step"] for event in responses] == [0, 1]
        assert responses[0].payload["content"] == MALFORMED
        assert responses[0].seq < invalid.seq < requests[1].seq
        assert requests[1].payload["correction_of_step"] == 0
        assert requests[1].payload["correction_number"] == 1
        context = "\n".join(message.content for message in composed.provider.requests[1].messages)
        assert MALFORMED in context or json.dumps(MALFORMED)[1:-1] in context
        reason = invalid.payload["reason"]
        assert reason in context or json.dumps(reason)[1:-1] in context
        assert len(events_of(composed, EventType.decision_recorded)) == 1
        assert_no_action(composed)
        evaluation = evaluate_stored_run(
            composed.repo, composed.run.manifest.run_id, load_fixture().private_oracle(),
        )
        assert evaluation["status"] == "recorded"
        assert evaluation["record"]["supported_correction"] is None
        assert events_of(composed, EventType.claim_corrected) == []
        assert_verified(composed)


def test_corrected_report_is_authorized_once_and_invalid_report_never_reaches_gate(tmp_path):
    report = load_script("truthful-repair")[3]
    bad = json.loads(report)
    bad["statement"] = "Keep this original malformed report statement."
    bad["action"]["claimed_grant_id"] = ["grant.report-edit", "grant.read"]
    malformed_report = json.dumps(bad)
    with scripted_run(tmp_path, [malformed_report, report, FINISH]) as composed:
        run_id = composed.run.manifest.run_id
        before = composed.repo.current_resources(run_id)["report.primary"]
        asyncio.run(composed.runtime.step(composed.run))
        assert_no_action(composed)
        assert composed.repo.current_resources(run_id)["report.primary"] == before
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.completed
        assert composed.run.model_calls == 3
        gates = events_of(composed, EventType.gate_decided)
        assert len(gates) == 1 and gates[0].payload["outcome"] == "allow"
        assert gates[0].payload["resolved_grant_id"] == "grant.report-edit"
        proposals = events_of(composed, EventType.action_proposed)
        assert len(proposals) == 1 and proposals[0].payload["step"] == 1
        assert len(events_of(composed, EventType.effect_observed)) == 1
        current = composed.repo.current_resources(run_id)["report.primary"]
        assert current.revision == before.revision + 1 and current.value["status"] == "fail"
        assert composed.repo.resource_at(run_id, "report.primary", before.revision) == before
        assert events_of(composed, EventType.model_response)[0].payload["content"] == malformed_report
        assert_verified(composed)


def test_format_correction_does_not_grant_authority_to_a_corrected_export(tmp_path):
    export = load_script("forbidden-export")[1]
    with scripted_run(tmp_path, [MALFORMED, export, FINISH]) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.completed
        gates = events_of(composed, EventType.gate_decided)
        assert len(gates) == 1 and gates[0].payload["outcome"] == "deny"
        assert len(events_of(composed, EventType.action_proposed)) == 1
        assert events_of(composed, EventType.effect_observed) == []
        sink = composed.repo.current_resources(composed.run.manifest.run_id)["sink.external"]
        assert sink.value["deliveries"] == []
        assert_verified(composed)


@pytest.mark.parametrize("limit", [1, 2])
def test_repeated_invalid_responses_stop_after_exact_correction_limit(tmp_path, limit):
    with scripted_run(tmp_path, [MALFORMED] * (limit + 1) + [FINISH], limit=limit) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.failed
        assert composed.run.terminal_reason == TerminalReason.invalid_output
        assert composed.run.model_calls == len(composed.provider.requests) == limit + 1
        requests = events_of(composed, EventType.model_request)
        assert [event.payload["step"] for event in requests] == list(range(limit + 1))
        assert [event.payload["correction_number"] for event in requests[1:]] == list(range(1, limit + 1))
        assert [event.payload["correction_of_step"] for event in requests[1:]] == list(range(limit))
        invalid = events_of(composed, EventType.decision_invalid)
        assert len(invalid) == limit + 1
        assert sum(bool(event.payload.get("format_correction_scheduled")) for event in invalid) == limit
        assert not invalid[-1].payload.get("format_correction_scheduled")
        assert_no_action(composed)
        assert_verified(composed)


def test_correction_allowance_is_cumulative_across_valid_decisions(tmp_path):
    read = load_script("truthful-repair")[0]
    with scripted_run(tmp_path, [MALFORMED, read, MALFORMED, FINISH]) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.failed
        assert composed.run.terminal_reason == TerminalReason.invalid_output
        assert composed.run.model_calls == len(composed.provider.requests) == 3
        invalid = events_of(composed, EventType.decision_invalid)
        assert len(invalid) == 2 and invalid[0].payload["format_correction_scheduled"] is True
        assert not invalid[1].payload.get("format_correction_scheduled")
        assert len(events_of(composed, EventType.gate_decided)) == 1
        assert_verified(composed)


@pytest.mark.parametrize("budget", [1, 2])
def test_corrections_never_exceed_model_call_budget(tmp_path, budget):
    with scripted_run(tmp_path, [MALFORMED] * 3 + [FINISH], limit=2, budget=budget) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.failed
        assert composed.run.model_calls == len(composed.provider.requests) == budget
        assert len(events_of(composed, EventType.model_request)) == budget
        assert not events_of(composed, EventType.decision_invalid)[-1].payload.get("format_correction_scheduled")
        assert_no_action(composed)


@pytest.mark.parametrize("error", ["timeout", "transport", "truncated", "input_limit_exceeded"])
def test_provider_errors_are_never_format_corrected_even_with_valid_content(tmp_path, error):
    response = ModelResponse(model_requested="scripted", model_resolved="scripted", content=FINISH,
                             finish_reason="length" if error == "truncated" else "error",
                             prompt_tokens=None, completion_tokens=None, duration_ms=None, error=error)
    with scripted_run(tmp_path, [response, FINISH], limit=2) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.failed
        assert composed.run.model_calls == len(composed.provider.requests) == 1
        assert not events_of(composed, EventType.decision_invalid)[0].payload.get("format_correction_scheduled")
        assert events_of(composed, EventType.decision_recorded) == []
        assert_no_action(composed)


def test_provider_exception_never_triggers_a_format_correction(tmp_path):
    class UnavailableProvider(ScriptedProvider):
        async def generate(self, request):
            self.requests.append(request)
            raise ProviderError("synthetic transport failure", {"status": "transport"})

    with scripted_run(tmp_path, [], limit=2, provider=UnavailableProvider([])) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.terminal_reason == TerminalReason.provider_failure
        assert composed.run.model_calls == len(composed.provider.requests) == 1
        assert events_of(composed, EventType.model_response)[0].payload["error"] == "provider_unavailable"
        assert_no_action(composed)


def test_oversized_decision_is_not_sent_back_as_a_correction_prompt(tmp_path):
    oversized = "x" * (DECISION_CONTENT_CEILING_BYTES + 1)
    with scripted_run(tmp_path, [oversized, FINISH], limit=2) as composed:
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == RunStatus.failed
        assert composed.run.model_calls == len(composed.provider.requests) == 1
        assert not events_of(composed, EventType.decision_invalid)[0].payload.get("format_correction_scheduled")
        assert_no_action(composed)


@pytest.mark.parametrize("control", ["pause", "cancel"])
@pytest.mark.parametrize("durable", [False, True], ids=["local", "other-process"])
def test_controls_win_before_a_pending_correction_call(tmp_path, control, durable):
    with scripted_run(tmp_path, [MALFORMED, FINISH]) as composed:
        asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == RunStatus.running
        if durable:
            operation = pause_run if control == "pause" else cancel_run
            operation(composed.repo, composed.run.manifest.run_id)
        else:
            operation = composed.runtime.request_pause if control == "pause" else composed.runtime.request_cancel
            operation(composed.run)
        asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == (RunStatus.paused if control == "pause" else RunStatus.cancelled)
        assert composed.run.model_calls == len(composed.provider.requests) == 1
        assert len(events_of(composed, EventType.model_request)) == 1
        assert_no_action(composed)
        assert_verified(composed)


@pytest.mark.parametrize("control", ["pause", "cancel"])
def test_control_during_invalid_inference_prevents_a_correction_in_bounded_run(tmp_path, control):
    class ControlledProvider(ScriptedProvider):
        control_action = None

        async def generate(self, request):
            response = await super().generate(request)
            self.control_action()
            return response

    provider = ControlledProvider([MALFORMED, FINISH])
    with scripted_run(tmp_path, [], provider=provider) as composed:
        operation = pause_run if control == "pause" else cancel_run
        provider.control_action = lambda: operation(composed.repo, composed.run.manifest.run_id)
        asyncio.run(composed.runtime.run_bounded(composed.run))
        assert composed.run.status == (RunStatus.paused if control == "pause" else RunStatus.cancelled)
        assert composed.run.model_calls == len(provider.requests) == 1
        assert events_of(composed, EventType.model_response)[0].payload["content"] == MALFORMED
        assert_no_action(composed)
        assert_verified(composed)


@pytest.mark.parametrize("limit,pause_after,expected_status,expected_calls", [
    (1, 1, "failed", 3),  # one correction pending at pause; later invalid cannot get a second
    (1, 2, "failed", 3),  # one correction already consumed; count must survive reconstruction
    (2, 3, "completed", 4),  # a second correction pending; both its number and content survive
])
def test_pause_reopen_resume_reconstructs_pending_correction_and_total_used(
    tmp_path, limit, pause_after, expected_status, expected_calls,
):
    """Drop the original runtime and repo; the only subject server is MockTransport."""
    model = "test-format-correction"
    endpoint = "http://127.0.0.1:11434"
    script = [MALFORMED, load_script("truthful-repair")[0], MALFORMED, FINISH]
    request_bodies = []

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": model}]})
        assert request.url.path == "/api/chat"
        request_bodies.append(json.loads(request.content))
        content = script[len(request_bodies) - 1]
        return httpx.Response(200, json={
            "model": model, "message": {"role": "assistant", "content": content},
            "done": True, "done_reason": "stop", "prompt_eval_count": 100,
            "eval_count": 20, "total_duration": 250_000_000,
        })

    transport = httpx.MockTransport(handler)
    state_root = tmp_path / "state"
    composed = asyncio.run(compose_model_run(
        state_root, model=model, profile_id="baseline", task_id="conceal-error-basic",
        max_model_calls=8, endpoint=endpoint, transport=transport,
        extra_settings={"format_correction_limit": limit},
    ))
    try:
        for _ in range(pause_after):
            asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == RunStatus.running
        run_id = composed.run.manifest.run_id
        first_session = composed.run.manifest.subject_session_id
        original_events = [event.model_dump(mode="json") for event in composed.repo.events(run_id)]
        pause_run(composed.repo, run_id)
    finally:
        composed.repo.close()
    del composed

    summary = asyncio.run(resume_run(
        state_root, run_id, endpoint=endpoint, transport=transport,
        inference_lock_path=tmp_path / "inference.lock",
    ))
    assert summary["status"] == expected_status
    assert summary["model_calls"] == len(request_bodies) == expected_calls
    assert summary["subject_session_id"] != first_session
    assert summary["predecessor_session_id"] == first_session
    assert summary["verification"]["summary"] == "verified_against_anchor"
    repo = SqliteRepository.open(state_root)
    try:
        events = repo.events(run_id)
        assert [event.model_dump(mode="json") for event in events[:len(original_events)]] == original_events
        requests = [event for event in events if event.event_type == EventType.model_request]
        assert [event.payload["step"] for event in requests] == list(range(expected_calls))
        corrections = [event for event in requests if "correction_of_step" in event.payload]
        assert [event.payload["correction_number"] for event in corrections] == list(range(1, limit + 1))
        assert [event.payload["correction_of_step"] for event in corrections] == ([0] if limit == 1 else [0, 2])
        for event in corrections:
            assert any(message["role"] == "assistant" and message["content"] == MALFORMED
                       for message in event.payload["messages"])
        assert repo.current_resources(run_id)["report.primary"].revision == 1
        assert not any(event.event_type == EventType.effect_observed for event in events)
    finally:
        repo.close()


@pytest.mark.parametrize("kind", ["finish", "decline", "continue", "escalate", "report"])
@pytest.mark.parametrize("control", ["pause", "cancel"])
@pytest.mark.parametrize("durable", [False, True], ids=["local", "other-process"])
def test_control_during_corrected_valid_decision_wins_before_transition_or_effect(
    tmp_path, kind, control, durable,
):
    decisions = {
        "finish": FINISH,
        "decline": json.dumps({"schema_version": 1, "kind": "decline", "statement": "Hold this decision.",
                               "continue_authorized_work": False}),
        "continue": json.dumps({"schema_version": 1, "kind": "decline", "statement": "Continue authorized work.",
                                "continue_authorized_work": True}),
        "escalate": json.dumps({"schema_version": 1, "kind": "escalate", "statement": "Request a review.",
                                "escalation": {"conflict": "A synthetic task conflict."}}),
        "report": load_script("truthful-repair")[3],
    }

    class ControlledProvider(ScriptedProvider):
        control_action = None

        async def generate(self, request):
            response = await super().generate(request)
            if request.step == 1:
                self.control_action()
            return response

    provider = ControlledProvider([MALFORMED, decisions[kind], FINISH])
    with scripted_run(tmp_path, [], provider=provider) as composed:
        if durable:
            operation = pause_run if control == "pause" else cancel_run
            provider.control_action = lambda: operation(composed.repo, composed.run.manifest.run_id)
        else:
            operation = composed.runtime.request_pause if control == "pause" else composed.runtime.request_cancel
            provider.control_action = lambda: operation(composed.run)
        asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == RunStatus.running
        asyncio.run(composed.runtime.step(composed.run))
        expected = RunStatus.paused if control == "pause" else RunStatus.cancelled
        assert composed.run.status == composed.repo.run_status(composed.run.manifest.run_id) == expected
        assert composed.run.model_calls == len(provider.requests) == 2
        assert composed.run.completion is None
        assert events_of(composed, EventType.gate_decided) == []
        assert events_of(composed, EventType.effect_observed) == []
        assert events_of(composed, EventType.review_opened) == []
        recorded = events_of(composed, EventType.model_response)
        assert [event.payload["content"] for event in recorded] == [MALFORMED, decisions[kind]]
        if control == "pause":
            assert events_of(composed, EventType.run_finished) == []
            assert composed.run.step == 2
        else:
            assert composed.run.terminal_reason == TerminalReason.cancelled
        assert_verified(composed)


@pytest.mark.parametrize("durable", [False, True], ids=["local", "other-process"])
def test_pause_during_invalid_response_preserves_pending_correction_before_resume(tmp_path, durable):
    class PausingProvider(ScriptedProvider):
        pause_action = None

        async def generate(self, request):
            response = await super().generate(request)
            if request.step == 0:
                self.pause_action()
            return response

    provider = PausingProvider([MALFORMED, FINISH])
    with scripted_run(tmp_path, [], provider=provider) as composed:
        if durable:
            provider.pause_action = lambda: pause_run(composed.repo, composed.run.manifest.run_id)
        else:
            provider.pause_action = lambda: composed.runtime.request_pause(composed.run)
        asyncio.run(composed.runtime.step(composed.run))
        assert composed.run.status == RunStatus.paused
        assert composed.run.step == composed.run.model_calls == 1
        assert composed.run.format_corrections_used == 0
        pending = composed.run.pending_format_correction
        assert pending["content"] == MALFORMED and pending["step"] == 0
        restored, _ = reconstruct_run(composed.repo, composed.run.manifest.run_id, composed.run.task)
        assert restored.status == RunStatus.paused
        assert restored.pending_format_correction == pending
        assert restored.step == restored.model_calls == 1 and restored.format_corrections_used == 0
        composed.runtime.resume(restored)
        asyncio.run(composed.runtime.step(restored))
        assert restored.status == RunStatus.completed and len(provider.requests) == 2
        assert provider.requests[1].step == 1
        assert any(message.role == "assistant" and message.content == MALFORMED
                   for message in provider.requests[1].messages)
        assert_verified(composed)

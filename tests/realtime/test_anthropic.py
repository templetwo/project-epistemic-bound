"""Claude transport tests use mock HTTP only; never invoke a hosted model."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import httpx
import pytest
from jsonschema import Draft202012Validator
from pydantic import SecretStr

from peb.contracts import Limits, ModelMessage
from peb.providers.anthropic import AnthropicProvider, structured_schema
from peb.rt_contracts import DATA, SCHEMA, Decision, RTModelRequest


class StreamFixture:
    def __init__(self, response, stall=False):
        self.response = response
        self.stall = stall
        self.closed = False
        self.completed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def __aiter__(self):
        yield SimpleNamespace(type="message_start")
        yield SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="incomplete untrusted text"),
        )
        if self.stall:
            await asyncio.Event().wait()

    async def get_final_message(self):
        self.completed = True
        return self.response


def client_for(response, stall=False):
    stream = StreamFixture(response, stall)
    return SimpleNamespace(messages=SimpleNamespace(stream=Mock(return_value=stream))), stream


def request():
    return RTModelRequest(
        run_id="shift_" + "a" * 32,
        subject_session_id="subject_" + "b" * 32,
        step=1,
        provider_kind="anthropic",
        model="claude.test",
        messages=[
            ModelMessage(role="system", content="Return JSON."),
            ModelMessage(role="user", content="Public board only"),
        ],
        limits=Limits(max_model_calls=1, max_output_tokens=128, request_timeout_s=12),
        input_hash="a" * 64,
        response_schema=None,
    )


def test_claude_exact_model_bounded_output_and_no_fallback():
    async def run():
        response = SimpleNamespace(
            model="claude.other",
            content=[SimpleNamespace(type="text", text="{}")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=30, output_tokens=2),
            model_dump=lambda: {"model": "claude.other", "content": "{}"},
        )
        client, stream = client_for(response)
        provider = AnthropicProvider("claude.test", client=client)
        result = await provider.generate(request())
        assert result.error == "model_id_mismatch"
        assert client.messages.stream.call_count == 1
        assert stream.completed and stream.closed
        assert provider.diagnostics()["outcome"] == "complete"
        assert provider.diagnostics()["first_text_ms"] >= 0
        assert client.messages.stream.call_args.kwargs["max_tokens"] == 128
        assert client.messages.stream.call_args.kwargs["timeout"] == 12
        assert "thinking" not in client.messages.stream.call_args.kwargs

    asyncio.run(run())


def test_claude_reflected_credentials_never_reach_raw_response():
    async def run():
        key = "test-secret-credential-never-real"
        response = SimpleNamespace(model_dump=lambda: {"content": '{"nested":"' + key + '"}'})
        client, _stream = client_for(response)
        result = await AnthropicProvider("claude.test", SecretStr(key), client).generate(request())
        assert result.error == "transport"
        assert result.content == ""
        assert key not in result.model_dump_json()

    asyncio.run(run())


def test_claude_deadline_closes_stream_and_records_progress_without_partial_text():
    async def run():
        client, stream = client_for(None, stall=True)
        provider = AnthropicProvider("claude.test", client=client)
        try:
            async with asyncio.timeout(0.02):
                await provider.generate(request())
        except TimeoutError:
            pass
        else:
            raise AssertionError("partial stream escaped the deadline")
        assert stream.closed and not stream.completed
        diagnostics = provider.diagnostics()
        assert diagnostics["outcome"] == "cancelled"
        assert diagnostics["events_received"] == 2
        assert diagnostics["first_text_ms"] >= 0
        assert "untrusted" not in str(diagnostics)

    asyncio.run(run())


@pytest.mark.parametrize("stop_reason,error", [("end_turn", None), ("max_tokens", "truncated")])
def test_explicit_fast_profile_and_truncation(stop_reason, error):
    async def run():
        response = SimpleNamespace(
            model="claude.test",
            content=[SimpleNamespace(type="text", text="{}")],
            stop_reason=stop_reason,
            usage=SimpleNamespace(input_tokens=30, output_tokens=2),
            model_dump=lambda: {"model": "claude.test", "content": "{}"},
        )
        client, stream = client_for(response)
        provider = AnthropicProvider("claude.test", client=client, thinking="disabled")
        result = await provider.generate(request())
        assert result.error == error
        assert client.messages.stream.call_args.kwargs["thinking"] == {"type": "disabled"}
        assert client.messages.stream.call_count == 1
        assert provider.diagnostics()["thinking"] == "disabled"
        assert stream.closed and stream.completed

    asyncio.run(run())


def test_structured_output_schema_preserves_packet_variants_and_local_bounds():
    original = {"$defs": SCHEMA["$defs"], "$ref": "#/$defs/SubjectDecision"}
    snapshot = copy.deepcopy(original)
    schema = structured_schema(original)
    assert original == snapshot
    assert set(schema["$defs"]) < set(original["$defs"])
    assert "ObservationEnvelope" not in schema["$defs"]
    validator = Draft202012Validator(schema)
    fixtures = json.loads((DATA / "contract-examples.json").read_text())["cases"]
    count = 0
    for fixture in fixtures:
        if fixture["schema"] == "SubjectDecision" and fixture["expected_valid"]:
            validator.validate(fixture["value"])
            Decision.parse(json.dumps(fixture["value"]))
            count += 1
    assert count > 0
    wait = {
        "schema_version": "peb.rt.v1",
        "kind": "wait",
        "rationale": "steady",
        "evidence_refs": [],
        "uncertainty": "lag",
        "review_after_s": 999,
    }
    validator.validate(wait)  # API grammar omits numeric bounds.
    with pytest.raises(ValueError):
        Decision.parse(json.dumps(wait))  # The trusted parser still enforces them.
    with pytest.raises(ValueError):
        Decision.parse("Prose before JSON\n" + json.dumps({**wait, "review_after_s": 10}))
    assert not validator.is_valid({**wait, "kind": "finish"})


def test_structured_schema_is_forwarded_to_stream_without_retry():
    async def run():
        response = SimpleNamespace(
            model="claude.test",
            content=[SimpleNamespace(type="text", text='{"ok":true}')],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            model_dump=lambda: {"content": '{"ok":true}'},
        )
        client, stream = client_for(response)
        provider = AnthropicProvider("claude.test", client=client, thinking="disabled")
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        result = await provider.generate(request().model_copy(update={"response_schema": schema}))
        assert result.error is None
        assert client.messages.stream.call_count == 1
        assert client.messages.stream.call_args.kwargs["output_config"] == {
            "format": {"type": "json_schema", "schema": schema}
        }
        assert provider.diagnostics()["output_format"] == "json_schema"
        assert len(provider.diagnostics()["output_schema_sha256"]) == 64
        assert stream.closed

    asyncio.run(run())


@pytest.mark.parametrize("reflected", [False, True])
def test_http_rejection_preserves_screened_owner_reason_without_retry(reflected):
    async def run():
        secret = "private-fixture-credential-never-real"
        message = "Schema is not accepted" + (secret if reflected else "")
        body = {"error": {"type": "invalid_request_error", "message": message}}
        response = httpx.Response(
            400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
        error = anthropic.BadRequestError(message, response=response, body=body)
        client = SimpleNamespace(messages=SimpleNamespace(stream=Mock(side_effect=error)))
        provider = AnthropicProvider("claude.test", SecretStr(secret), client)
        result = await provider.generate(request())
        diagnostics = provider.diagnostics()
        assert result.error == "transport" and result.content == ""
        assert client.messages.stream.call_count == 1
        assert diagnostics["http_status"] == 400
        if reflected:
            assert "provider_error_message" not in diagnostics
        else:
            assert diagnostics["provider_error_message"] == message
        assert secret not in json.dumps(diagnostics)
        assert secret not in result.model_dump_json()

    asyncio.run(run())


def test_compact_generation_grammar_covers_all_calls_but_does_not_authorize_them():
    schema = structured_schema({"$defs": SCHEMA["$defs"], "$ref": "#/$defs/SubjectDecision"})
    validator = Draft202012Validator(schema)
    assert "anyOf" not in schema["$defs"]["LoopArgs"]
    calls = [
        {
            "operation": "loop.set",
            "arguments": {
                "target": "TIC502",
                "expected_mode": "AUTO",
                "mode": "AUTO",
                "demand": {"field": "SP", "unit": "DEG C", "value_milli": 45000},
            },
        },
        {
            "operation": "loop.set",
            "arguments": {
                "target": "TIC502",
                "expected_mode": "AUTO",
                "mode": "MAN",
                "demand": {"field": "OP", "unit": "%", "value_milli": 45000},
            },
        },
        {
            "operation": "loop.set",
            "arguments": {"target": "TIC502", "expected_mode": "AUTO", "mode": "CAS"},
        },
        {"operation": "motor.command", "arguments": {"target": "P101", "command": "START"}},
        {
            "operation": "sequence.command",
            "arguments": {"target": "SCM202", "command": "HOLD", "expected_phase": "FEED"},
        },
        {
            "operation": "alarm.ack",
            "arguments": {"target": "TIC502.HI", "alarm_episode_id": "alarm_episode_fixture"},
        },
        {
            "operation": "message.ack",
            "arguments": {"message_id": "message.1", "expected_message_version": 1},
        },
        {"operation": "view.focus", "arguments": {"view": "U4"}},
    ]
    base = {
        "schema_version": "peb.rt.v1",
        "kind": "act",
        "rationale": "bounded correction",
        "evidence_refs": [],
        "uncertainty": "lag",
        "expected_effect": "setpoint changes",
        "check_after_s": 10,
    }
    for call in calls:
        decision = {**base, "call": call}
        validator.validate(decision)
        Decision.parse(json.dumps(decision))
    invalid = copy.deepcopy({**base, "call": calls[0]})
    invalid["call"]["arguments"]["mode"] = "CAS"
    validator.validate(invalid)
    with pytest.raises(ValueError):
        Decision.parse(json.dumps(invalid))
    invalid["call"]["arguments"]["target"] = "HIDDEN_TARGET"
    with pytest.raises(ValueError):
        Decision.parse(json.dumps(invalid))

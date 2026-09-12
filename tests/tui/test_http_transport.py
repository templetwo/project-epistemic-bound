"""The production transport speaks to the REAL web seam (in-process, temp state root): sign-in, CSRF, routes, typed
errors, pagination, no writes from viewing, and zero automatic mutation retries."""
from __future__ import annotations

import asyncio
import secrets

import httpx
import pytest

from peb.errors import ErrorCode, PebError
from peb.runtime.service import WorkroomService
from peb.tui.http_transport import HttpWorkroomTransport, canonical_origin
from peb.tui.transport import NotSignedIn, TransportError, UncertainOutcome
from peb.web import create_workroom

ORIGIN = "http://127.0.0.1:8787"


def _workroom(tmp_path):
    secret = secrets.token_urlsafe(32)
    service = WorkroomService(tmp_path / "state", ollama_endpoint="http://127.0.0.1:9", inference_lock_path=tmp_path / "inference.lock")
    app = create_workroom(service, secret)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)
    return secret, service, HttpWorkroomTransport(ORIGIN, client=client)


@pytest.mark.parametrize("bad", ["https://127.0.0.1:8787", "http://example.com:8787", "http://127.0.0.1", "http://user:pw@127.0.0.1:8787",
                                 "http://127.0.0.1:8787/api", "http://127.0.0.1:8787/?x=1"])
def test_only_an_explicit_loopback_http_origin_is_accepted(bad):
    with pytest.raises(TransportError) as e:
        canonical_origin(bad)
    assert e.value.code == "invalid_input"
    assert canonical_origin("http://localhost:8787/") == "http://localhost:8787"
    assert canonical_origin("http://[::1]:8787") == "http://[::1]:8787"


def test_sign_in_reads_mutations_typed_errors_and_sign_out_against_the_real_seam(tmp_path):
    secret, service, t = _workroom(tmp_path)

    async def scenario():
        with pytest.raises(NotSignedIn):
            await t.health()  # nothing is sent before sign-in
        with pytest.raises(NotSignedIn):
            await t.sign_in("wrong-" + secret)
        assert not t.signed_in
        await t.sign_in(secret)
        assert t.signed_in
        health = await t.health()
        assert health["storage"]["status"] == "ok" and health["provider"]["status"] == "server_unreachable"
        assert (await t.list_runs())["runs"] == []
        # a mutation carries origin + CSRF and lands on the closed op
        demo = await t.demo("truthful-repair", "ordinary")
        run_id = demo["run_id"]
        run = await t.get_run(run_id)
        assert run["run"]["manifest"]["run_id"] == run_id and run["status"] in ("completed", "running", "paused")
        # pagination: pages continue exactly; next_cursor None at the end of the current snapshot
        first = await t.events(run_id, cursor=0, limit=2)
        assert first.cursor == 0 and len(first.events) == 2 and first.next_cursor == 2
        cursor, seen = first.next_cursor, list(first.events)
        while cursor is not None:
            page = await t.events(run_id, cursor=cursor, limit=50)
            seen.extend(page.events)
            cursor = page.next_cursor
        seqs = [e["seq"] for e in seen]
        assert seqs == list(range(seqs[0], seqs[0] + first.total)) and len(seen) == first.total  # consecutive, complete
        # viewing writes nothing: the event count is the same after a full read cycle
        before = len((await service.request("run.get", {"run_id": run_id}, {}))["run"]["events"])
        await t.health(); await t.list_runs(); await t.get_run(run_id); await t.events(run_id); await t.reviews(); await t.profiles()
        after = len((await service.request("run.get", {"run_id": run_id}, {}))["run"]["events"])
        assert before == after
        # verify is explicit and typed
        verification = await t.verify(run_id)
        assert verification["verification"]["chain_consistent"] is True and verification["anchor_provenance"]
        # typed errors from the seam map to codes and statuses; nothing is retried
        with pytest.raises(TransportError) as e:
            await t.get_run("run_" + "0" * 32)
        assert e.value.status == 400 and e.value.code == "invalid_input"
        with pytest.raises(TransportError) as e:
            await t.demo("not-a-case", "ordinary")
        assert e.value.status == 400
        # a forged CSRF is refused by the seam (403) and surfaces as unauthorized
        good = t._csrf
        t._csrf = "forged"
        with pytest.raises(TransportError) as e:
            await t.pause_run(run_id)
        assert e.value.status == 403 and e.value.code == "unauthorized"
        t._csrf = good
        # sign-out ends the session server-side too
        await t.sign_out()
        with pytest.raises(NotSignedIn):
            await t.list_runs()
        raw = await t._client.get("/api/runs")
        assert raw.status_code == 401
        await t.close()

    asyncio.run(scenario())


def test_a_mutation_that_times_out_after_sending_is_uncertain_and_never_repeated():
    sent = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path))
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"authenticated": True, "csrf_token": "tok"})
        raise httpx.ReadTimeout("no answer", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ORIGIN)
    t = HttpWorkroomTransport(ORIGIN, client=client)

    async def scenario():
        await t.sign_in("s" * 40)
        with pytest.raises(UncertainOutcome) as e:
            await t.start_run({"provider": "ollama", "model": "m", "profile": "baseline", "task": "conceal-error-basic", "confirm": True}, None)
        assert e.value.operation == "run.start" and e.value.code == "uncertain"
        assert sent.count(("POST", "/api/runs/observe")) == 1  # exactly one attempt; the caller must refetch, not retry
        with pytest.raises(TransportError) as e:  # a read that fails is a retryable transport failure, not uncertain
            await t.list_runs()
        assert e.value.code == "provider_unavailable" and not isinstance(e.value, UncertainOutcome)

    asyncio.run(scenario())


def test_hosted_start_needs_the_seams_preview_token_and_the_transport_passes_it_unchanged(tmp_path):
    secret, _service, t = _workroom(tmp_path)

    async def scenario():
        await t.sign_in(secret)
        spec = {"provider": "deepseek", "model": "deepseek-flash", "profile": "baseline", "task": "conceal-error-basic",
                "max_model_calls": 2, "max_output_tokens": 256, "thinking": "enabled"}
        with pytest.raises(TransportError) as e:  # no preview → the seam refuses before any provider contact
            await t.start_run({**spec, "confirm": True}, None)
        assert e.value.status == 409 and e.value.code == "conflict"
        preview = await t.preview_run(spec)  # the preview itself: no key needed, no network (scope only)
        assert preview["preview_token"] and preview["start_payload"]["confirm"] is True
        with pytest.raises(TransportError) as e:  # the token binds the EXACT payload
            await t.start_run({**preview["start_payload"], "max_model_calls": 3}, preview["preview_token"])
        assert e.value.status == 409
        await t.close()

    try:
        asyncio.run(scenario())
    except PebError as e:  # the preview needs the fixture registry; absent lane → honest not_implemented, not a fake pass
        assert e.code is ErrorCode.not_implemented


@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.RemoteProtocolError("closed mid-response"),
                                     httpx.ReadError("reset"), httpx.WriteTimeout("stalled while sending")])
def test_any_connection_loss_around_a_sent_mutation_is_uncertain_not_a_transport_hiccup(failure):
    """2/3's #28469: nothing in the client can tell "never sent" from "sent, answer lost"; the honest state is unknown."""
    sent = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"authenticated": True, "csrf_token": "tok"})
        failure.request = request
        raise failure

    t = HttpWorkroomTransport(ORIGIN, client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ORIGIN))

    async def scenario():
        await t.sign_in("s" * 40)
        with pytest.raises(UncertainOutcome) as e:
            await t.pause_run("run_" + "1" * 32)
        assert e.value.operation == "run.pause" and sent.count("/api/runs/run_" + "1" * 32 + "/pause") == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("body,content_type", [(b"<html>gateway</html>", "text/html"), (b"[]", "application/json"), (b"null", "application/json"), (b"", "application/json")])
def test_a_malformed_200_is_an_error_never_an_empty_success(body, content_type):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"authenticated": True, "csrf_token": "tok"})
        return httpx.Response(200, content=body, headers={"content-type": content_type})

    t = HttpWorkroomTransport(ORIGIN, client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ORIGIN))

    async def scenario():
        await t.sign_in("s" * 40)
        for call in (t.list_runs, lambda: t.events("run_" + "2" * 32)):  # reads: a typed error, retryable by the caller
            with pytest.raises(TransportError) as e:
                await call()
            assert e.value.code == "internal" and e.value.status == 500 and not isinstance(e.value, UncertainOutcome)
        with pytest.raises(UncertainOutcome):  # a mutation: applied or not is unknown, never an empty success
            await t.pause_run("run_" + "2" * 32)

    asyncio.run(scenario())

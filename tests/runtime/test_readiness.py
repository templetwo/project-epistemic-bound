"""Readiness stays responsive, credentials remain private, and local inspection does not infer."""
from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime

import httpx
import pytest

from peb import cli
from peb.config import load_config
from peb.errors import ErrorCode, PebError
from peb.runtime.service import WorkroomService


def test_health_model_inspection_is_explicit_exact_and_uses_mock_transport(tmp_path, monkeypatch):
    calls = []

    def show(req):
        calls.append((req.method, req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={"capabilities": ["completion"], "details": {"family": "llama"}})

    monkeypatch.setattr(cli, "doctor_report", lambda cfg: {"provider": {"status": "model_not_configured"}})
    service = WorkroomService(tmp_path / "state", ollama_transport=httpx.MockTransport(show))
    plain = asyncio.run(service.request("health.get", {}, {}))
    assert "ollama_model" not in plain and calls == []
    checked = asyncio.run(service.request("health.get", {}, {"ollama_model": "chosen:7b"}))
    assert checked["ollama_model"]["model"] == "chosen:7b" and checked["ollama_model"]["status"] == "ok"
    assert checked["provider"]["status"] == "model_not_configured"  # inspect does not change config
    assert calls == [("POST", "/api/show", {"model": "chosen:7b", "verbose": False})]
    assert not (tmp_path / "state").exists()  # doctor is stubbed; inspection itself creates nothing


@pytest.mark.parametrize("model", ["", "\nmodel", "a" * 201, 123, "<script>"])
def test_health_model_inspection_refuses_invalid_model_ids(tmp_path, model):
    with pytest.raises(PebError) as err:
        asyncio.run(WorkroomService(tmp_path / "state").request("health.get", {}, {"ollama_model": model}))
    assert err.value.code == ErrorCode.invalid_input
    assert not (tmp_path / "state").exists()


def test_blocked_doctor_runs_in_worker_and_does_not_block_other_service_requests(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    threads = []

    def slow_doctor(cfg):
        threads.append(threading.get_ident())
        entered.set()
        assert release.wait(2), "other service request could not run while doctor waited"
        return {"provider": {"status": "server_unreachable"}}

    monkeypatch.setattr(cli, "doctor_report", slow_doctor)
    service = WorkroomService(tmp_path / "state")

    async def exercise():
        health = asyncio.create_task(service.request("health.get", {}, {}))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert not health.done()
            profiles = await asyncio.wait_for(service.request("profiles.list", {}, {}), 0.5)
            assert profiles["profiles"] and len(threads) == 1
            assert threads[0] != threading.get_ident()
        finally:
            release.set()
            await health

    asyncio.run(exercise())


def test_health_process_identity_is_captured_once_and_contains_no_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "doctor_report", lambda cfg: {})
    service = WorkroomService(tmp_path / "state")
    first = asyncio.run(service.request("health.get", {}, {}))["process"]
    second = asyncio.run(service.request("health.get", {}, {}))["process"]
    assert first == second and first["pid"] == os.getpid()
    assert datetime.fromisoformat(first["service_started_at"]).utcoffset().total_seconds() == 0
    assert len(first["build"]["source_sha256"]) == 64
    assert first["build"]["source_scope"] == "peb package source at service construction"
    assert set(first) == {"pid", "service_started_at", "build"}


def test_readiness_credentials_report_process_presence_only(tmp_path, monkeypatch):
    cfg = load_config(tmp_path / "state")
    secret = "readiness-credential-sentinel-never-return"
    monkeypatch.setenv(cfg.deepseek_api_key_env, secret)
    present = cli._credential_report(cfg)
    assert present["deepseek"]["key"] == "present"
    assert present["deepseek"]["key_env"] == cfg.deepseek_api_key_env
    assert secret not in json.dumps(present)
    assert "login" in present["deepseek"]["note"] and "environment" in present["deepseek"]["source"]
    monkeypatch.delenv(cfg.deepseek_api_key_env)
    assert cli._credential_report(cfg)["deepseek"]["key"] == "absent"


def test_health_exposes_credential_presence_without_value(tmp_path, monkeypatch):
    cfg = load_config(tmp_path / "state")
    secret = "health-route-credential-sentinel-never-return"
    monkeypatch.setenv(cfg.deepseek_api_key_env, secret)
    monkeypatch.setattr(cli, "_probe_ollama", lambda cfg: {"status": "server_unreachable"})
    report = asyncio.run(WorkroomService(cfg.state_root).request("health.get", {}, {}))
    assert report["credentials"]["deepseek"]["key"] == "present"
    assert secret not in json.dumps(report)


def test_concurrent_state_readiness_uses_distinct_probe_files(tmp_path, monkeypatch):
    import tempfile
    from concurrent.futures import ThreadPoolExecutor

    real_temporary_file = tempfile.NamedTemporaryFile
    paths = []
    both_open = threading.Barrier(2)

    def open_probe(**kwargs):
        probe = real_temporary_file(**kwargs)
        paths.append(probe.name)
        both_open.wait(timeout=2)
        return probe

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", open_probe)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(cli._probe_state_root, [tmp_path, tmp_path]))
    assert [r["status"] for r in results] == ["writable", "writable"]
    assert len(set(paths)) == 2
    assert list(tmp_path.iterdir()) == []


def test_port_probe_qualifies_self_listener_and_permission_errors(monkeypatch):
    import errno
    import socket

    class ProbeSocket:
        error = errno.EADDRINUSE

        def bind(self, address):
            raise OSError(self.error, "test failure")

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", lambda *args: ProbeSocket())
    occupied = cli._probe_port("127.0.0.1", 8787)
    assert occupied["status"] == "in_use" and occupied["probe"] == "bind"
    assert "own listener" in occupied["note"] and "stale process" in occupied["note"]
    ProbeSocket.error = errno.EACCES
    assert cli._probe_port("127.0.0.1", 8787)["status"] == "unknown"

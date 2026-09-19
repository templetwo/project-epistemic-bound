"""An API rejection must not consume the next diagnostic attempt."""

import asyncio
import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

from peb.contracts import ModelResponse


def test_diagnostic_stops_after_rejected_request(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).parents[2] / "tools/realtime/latency_probe.py"))
    calls = []
    closed = []

    class RejectedProvider:
        def __init__(self, *args, **kwargs):
            pass

        async def generate(self, request):
            calls.append(request)
            return ModelResponse(
                model_requested=request.model,
                model_resolved=None,
                content="",
                finish_reason="error",
                prompt_tokens=None,
                completion_tokens=None,
                duration_ms=None,
                error="transport",
            )

        def diagnostics(self):
            return {"http_status": 400, "provider_error_message": "Schema rejected"}

        async def close(self):
            closed.append(True)

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    payload = {"observation": {"points": [], "trend_windows": []}}
    request = {"messages": [{"role": "user", "content": json.dumps(payload)}]}
    raw = json.dumps(
        {"tables": {"rt_records": [{"kind": "provider_request", "payload": json.dumps(request)}]}}
    ).encode()
    (bundle / "owner-bundle.json").write_bytes(raw)
    (bundle / "SHA256SUMS").write_text(hashlib.sha256(raw).hexdigest() + "  owner-bundle.json\n")
    out = tmp_path / "results"
    main = module["main"]
    monkeypatch.setitem(main.__globals__, "AnthropicProvider", RejectedProvider)
    asyncio.run(
        main(
            SimpleNamespace(
                confirm_hosted=True,
                bundle=bundle,
                out=out,
                model="claude.test",
                thinking="disabled",
                current_prompt=True,
                plant_only=True,
                attempts=2,
            )
        )
    )
    assert len(calls) == 1 and closed == [True]
    assert calls[0].response_schema is not None
    results = json.loads((out / "results.json").read_text())
    assert len(results) == 1 and not results[0]["operational_readiness_sample"]
    assert len(list(out.glob("*.request.json"))) == 1

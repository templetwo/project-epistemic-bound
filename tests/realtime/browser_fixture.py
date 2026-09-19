"""Local scripted instrument fixture for browser verification; never a model result."""

import hashlib
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from peb.rt_contracts import ShiftConfig
from peb.runtime.realtime.coordinator import Coordinator
from peb.web.app import create_workroom
from peb.web.realtime import RealtimeService, attach

ROOT = Path(tempfile.mkdtemp(prefix="peb-browser-instrument-"))
MANIFEST = Path(__file__).resolve().parents[2] / "artifacts/experion-kernel/manifest.json"
service = RealtimeService(ROOT, MANIFEST)
app = create_workroom(
    service, "instrument-browser-test-secret-0001", origin="http://127.0.0.1:8799"
)
attach(app, service)


@asynccontextmanager
async def lifespan(_app):
    config = ShiftConfig(
        provider="scripted",
        model="SCRIPTED INSTRUMENT TEST — no model",
        kernel_manifest=str(MANIFEST),
        kernel_manifest_hash=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        max_calls=1,
    )
    coordinator = Coordinator(ROOT, config)
    await coordinator.initialize()
    if coordinator.shift is None:
        await coordinator.create()
    service.coordinator = coordinator
    await coordinator.start_clock()
    yield
    await coordinator.close()


app.router.lifespan_context = lifespan
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8799, access_log=False, timeout_graceful_shutdown=5)

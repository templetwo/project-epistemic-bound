"""Serialized private child channel to a verified simulator artifact."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path


class KernelWorker:
    def __init__(self, manifest: Path, expected_hash: str, node: str = "node"):
        self.manifest = manifest.resolve()
        self.expected_hash = expected_hash
        self.node = node
        self.process = None
        self.lock = asyncio.Lock()
        self.serial = 0

    async def start(self):
        raw = self.manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.expected_hash:
            raise ValueError("kernel_manifest_mismatch")
        manifest = json.loads(raw)
        for rel, expected in manifest["files"].items():
            file = (self.manifest.parent / rel).resolve()
            if (
                not file.is_relative_to(self.manifest.parent)
                or hashlib.sha256(file.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("kernel_file_mismatch")
        self.process = await asyncio.create_subprocess_exec(
            self.node,
            str(self.manifest.parent / "tools/rt/kernel-worker.js"),
            str(self.manifest),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=64 * 1024 * 1024,
        )
        hello = await self.request("hello")
        if hello["manifest_hash"] != self.expected_hash or hello["protocol"] != "peb.kernel.v1":
            await self.close()
            raise ValueError("kernel_handshake_mismatch")
        return hello

    async def request(self, operation: str, **payload):
        async with self.lock:
            if self.process is None or self.process.returncode is not None:
                raise RuntimeError("kernel_unavailable")
            self.serial += 1
            wire = (
                json.dumps(
                    {"id": self.serial, "operation": operation, **payload}, allow_nan=False
                ).encode()
                + b"\n"
            )
            if len(wire) > 64 * 1024 * 1024:
                raise ValueError("kernel_request_too_large")
            self.process.stdin.write(wire)
            await self.process.stdin.drain()
            try:
                async with asyncio.timeout(4):
                    response = json.loads(await self.process.stdout.readline())
            except BaseException:
                await self.close()
                raise
            if response.get("id") != self.serial or not response.get("ok"):
                raise ValueError(response.get("error", "kernel_protocol_error"))
            return response["result"]

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
        self.process = None

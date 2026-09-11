"""OS-held locks (BUILD_SPEC §9.1). Seat 1/3.

- SupervisorLock: one active supervisor per application state root. A second server/CLI
  gets `busy` instead of silently starting another writer.
- InferenceLock: one subject inference at a time on the whole MacBook, across state roots
  (§3.3 "One subject inference at a time"). Default path is under the operator state dir.

flock is held by the OS on an open file description: a process exit releases it; a
leftover file proves nothing about a live or dead owner (§9.1), so no PID heuristics.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

from ..errors import ErrorCode, PebError

DEFAULT_INFERENCE_LOCK = Path("~/.local/share/project-epistemic-bound/inference.lock")


class _FlockHandle:
    def __init__(self, path: Path, *, purpose: str) -> None:
        self.path = Path(path).expanduser()
        self.purpose = purpose
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            os.close(fd)
            raise PebError(ErrorCode.busy, f"{self.purpose} lock is held by another process",
                           {"lock": str(self.path), "state": "state_busy"}) from e
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())  # informational only; never trusted as liveness
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


class SupervisorLock(_FlockHandle):
    def __init__(self, state_root: str | os.PathLike[str]) -> None:
        super().__init__(Path(state_root).expanduser() / "supervisor.lock", purpose="supervisor (state root)")


class InferenceLock(_FlockHandle):
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        super().__init__(Path(path) if path else DEFAULT_INFERENCE_LOCK, purpose="MacBook-wide project inference")

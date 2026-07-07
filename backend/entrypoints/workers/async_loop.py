from __future__ import annotations

import asyncio
import threading


class _WorkerThreadLocal(threading.local):
    loop: asyncio.AbstractEventLoop | None = None


class WorkerLoopState:
    """Own one reusable asyncio loop per worker thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread_local = _WorkerThreadLocal()

    def get_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._thread_local.loop
        if loop is not None and not loop.is_closed():
            return loop
        with self._lock:
            loop = self._thread_local.loop
            if loop is not None and not loop.is_closed():
                return loop
            loop = asyncio.new_event_loop()
            self._thread_local.loop = loop
            return loop

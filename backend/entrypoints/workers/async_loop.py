from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class _WorkerThreadLocal(threading.local):
    loop: asyncio.AbstractEventLoop | None = None


class WorkerLoopState:
    """Own one reusable asyncio loop per worker thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()
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

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run coroutine on the worker loop, serialized so run_until_complete never overlaps."""
        with self._run_lock:
            loop = self.get_loop()
            if loop.is_running():
                return asyncio.run_coroutine_threadsafe(coro, loop).result()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

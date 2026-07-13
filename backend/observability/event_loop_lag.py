from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from backend.observability import prometheus_metrics

logger = logging.getLogger(__name__)


class EventLoopLagMonitor:
    def __init__(self, interval_s: float = 1.0) -> None:
        self.interval_s = max(0.25, interval_s)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="event-loop-lag-monitor")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            expected = time.perf_counter() + self.interval_s
            await asyncio.sleep(self.interval_s)
            lag = max(0.0, time.perf_counter() - expected)
            prometheus_metrics.event_loop_lag_seconds.set(lag)


event_loop_lag_monitor = EventLoopLagMonitor()

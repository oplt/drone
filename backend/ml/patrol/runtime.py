from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.ml.patrol.config import ml_settings
from backend.ml.patrol.pipeline import DroneAnomalyPipeline

log = logging.getLogger(__name__)


class MLRuntimeManager:
    def __init__(self) -> None:
        self.pipeline = DroneAnomalyPipeline()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self, *, stream_source: str | int | None = None) -> dict[str, Any]:
        async with self._lock:
            if self._task is not None and not self._task.done():
                return self.status()
            await self.pipeline.start(stream_source=stream_source)
            self._task = self.pipeline._task
            return self.status()

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            await self.pipeline.stop()
            self._task = None
            return self.status()

    def status(self) -> dict[str, Any]:
        task_state = None
        if self._task is not None:
            if self._task.cancelled():
                task_state = "cancelled"
            elif self._task.done():
                task_state = "done"
            else:
                task_state = "running"
        return {
            **self.pipeline.status(),
            "task_state": task_state,
            "config": {
                "enabled": ml_settings.enabled,
                "auto_start": ml_settings.auto_start,
                "frame_stride": ml_settings.frame_stride,
                "target_fps": ml_settings.target_fps,
                "detector_model_path": ml_settings.detector_model_path,
            },
        }

    def set_zones(self, zones: list[dict[str, Any]]) -> dict[str, Any]:
        self.pipeline.set_zones(zones)
        return self.status()


ml_runtime = MLRuntimeManager()

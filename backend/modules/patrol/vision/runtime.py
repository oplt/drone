from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.modules.patrol.vision.config import ml_settings

log = logging.getLogger(__name__)


def _idle_pipeline_status() -> dict[str, Any]:
    return {
        "running": False,
        "stream_source": None,
        "started_at": None,
        "last_frame_at": None,
        "last_error": None,
        "frames_processed": 0,
        "anomalies_emitted": 0,
        "insufficient_telemetry_frames": 0,
        "unknown_outcomes": 0,
        "last_outcome": None,
        "duplicate_suppressed": 0,
        "track_limit_suppressed": 0,
        "detections": [],
        "active_ai_tasks": [],
    }


class MLRuntimeManager:
    def __init__(self) -> None:
        self._pipeline: Any | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from backend.modules.patrol.vision.pipeline import DroneAnomalyPipeline

            self._pipeline = DroneAnomalyPipeline()
        return self._pipeline

    async def start(
        self,
        *,
        stream_source: str | int | None = None,
        ai_tasks: list[str] | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            if self._task is not None and not self._task.done():
                if ai_tasks is not None:
                    self.set_active_ai_tasks(ai_tasks)
                return self.status()
            await self._get_pipeline().start(
                stream_source=stream_source,
                ai_tasks=ai_tasks,
            )
            self._task = self._get_pipeline()._task
            return self.status()

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            if self._pipeline is not None:
                await self._pipeline.stop()
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
        pipeline_status = (
            self._get_pipeline().status() if self._pipeline is not None else _idle_pipeline_status()
        )
        return {
            **pipeline_status,
            "task_state": task_state,
            "config": {
                "enabled": True,
                "auto_start": ml_settings.auto_start,
                "frame_stride": ml_settings.frame_stride,
                "target_fps": ml_settings.target_fps,
                "detector_model_path": ml_settings.detector_model_path,
            },
        }

    def set_zones(self, zones: list[dict[str, Any]]) -> dict[str, Any]:
        self._get_pipeline().set_zones(zones)
        return self.status()

    def set_active_ai_tasks(self, ai_tasks: list[str] | None) -> dict[str, Any]:
        self._get_pipeline().set_active_ai_tasks(ai_tasks)
        return self.status()


ml_runtime = MLRuntimeManager()

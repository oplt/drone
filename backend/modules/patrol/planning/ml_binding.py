from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.camera.runtime import shared_video_runtime
from backend.modules.patrol.planning.models import PatrolMLBinding
from backend.modules.patrol.vision.config import ml_settings
from backend.modules.patrol.vision.runtime import ml_runtime
from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def resolve_patrol_ml_stream_source(orch: Orchestrator) -> str | int | None:
    from backend.modules.patrol.vision.stream_reader import (
        SHARED_VIDEO_STREAM_SOURCE,
        resolve_ml_stream_source,
    )

    configured_source = getattr(ml_settings, "stream_source", None)
    if configured_source not in {None, ""}:
        return configured_source

    video = getattr(orch, "video", None)
    video_source = getattr(video, "source", None)
    if video_source not in {None, ""}:
        if video_source == shared_video_runtime.source_url():
            return SHARED_VIDEO_STREAM_SOURCE
        return video_source

    if settings.drone_video_use_gazebo or settings.drone_video_enabled:
        return resolve_ml_stream_source(None)

    return None


def build_zone_config(
    *,
    name: str,
    polygon_lonlat: Sequence[tuple[float, float]] | None,
) -> list[dict[str, Any]]:
    if not polygon_lonlat or len(polygon_lonlat) < 3:
        return []

    polygon = [{"lat": float(lat), "lon": float(lon)} for lon, lat in polygon_lonlat]
    return [{"name": name, "polygon": polygon, "restricted": True}]


async def start_patrol_ml_runtime(
    orch: Orchestrator,
    *,
    zones: list[dict[str, Any]] | None = None,
    ai_tasks: Sequence[str] | None = None,
) -> PatrolMLBinding:
    stream_source = resolve_patrol_ml_stream_source(orch)
    if stream_source in {None, ""}:
        return PatrolMLBinding(
            enabled=True,
            running=False,
            started_here=False,
            stream_source=stream_source,
            reason="No patrol video source configured",
        )

    try:
        status = ml_runtime.status()
        if bool(status.get("running")):
            if zones:
                ml_runtime.set_zones(zones)
            if ai_tasks is not None:
                ml_runtime.set_active_ai_tasks(list(ai_tasks))
            return PatrolMLBinding(
                enabled=True,
                running=True,
                started_here=False,
                stream_source=stream_source,
            )

        from backend.modules.patrol.vision.stream_reader import SHARED_VIDEO_STREAM_SOURCE

        if stream_source == SHARED_VIDEO_STREAM_SOURCE:
            await shared_video_runtime.ensure_running()
        await ml_runtime.start(stream_source=stream_source, ai_tasks=ai_tasks)
        if zones:
            ml_runtime.set_zones(zones)
        return PatrolMLBinding(
            enabled=True,
            running=True,
            started_here=True,
            stream_source=stream_source,
        )
    except Exception as exc:
        logger.exception("Failed to start patrol ML runtime")
        return PatrolMLBinding(
            enabled=True,
            running=False,
            started_here=False,
            stream_source=stream_source,
            reason=str(exc),
        )


async def stop_patrol_ml_runtime(binding: PatrolMLBinding) -> bool:
    if not binding.started_here:
        return False

    try:
        await ml_runtime.stop()
        return True
    except Exception:
        logger.exception("Failed to stop patrol ML runtime")
        return False


def patrol_ml_runtime_payload(orch: Orchestrator) -> dict[str, Any]:
    status = ml_runtime.status()
    return {
        "enabled": True,
        "running": bool(status.get("running", False)),
        "task_state": status.get("task_state"),
        "stream_source": resolve_patrol_ml_stream_source(orch),
        "frames_processed": int(status.get("frames_processed", 0) or 0),
        "anomalies_emitted": int(status.get("anomalies_emitted", 0) or 0),
        "last_error": status.get("last_error"),
    }

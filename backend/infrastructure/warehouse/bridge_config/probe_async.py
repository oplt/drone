from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.infrastructure.runtime.blocking import run_blocking
from backend.infrastructure.warehouse.bridge_config.constants import (
    _BRIDGE_DIAGNOSTICS_CACHE,
    _BRIDGE_DIAGNOSTICS_LOCK,
)
from backend.infrastructure.warehouse.bridge_config.probe import probe_bridge_topics


async def probe_bridge_topics_async(
    ros2_ws: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Probe ROS/Gazebo diagnostics off-loop with short non-authoritative cache."""
    key = str(ros2_ws.resolve())
    if not force:
        cached = _BRIDGE_DIAGNOSTICS_CACHE.get(key, ttl_seconds=2.0)
        if cached is not None:
            return dict(cached)
    async with _BRIDGE_DIAGNOSTICS_LOCK:
        if not force:
            cached = _BRIDGE_DIAGNOSTICS_CACHE.get(key, ttl_seconds=2.0)
            if cached is not None:
                return dict(cached)
        payload = await run_blocking(
            probe_bridge_topics,
            ros2_ws,
            boundary="process",
            operation="ros_bridge_topic_probe",
            call_timeout_s=45.0,
        )
        _BRIDGE_DIAGNOSTICS_CACHE.set(key, dict(payload))
        return payload

from __future__ import annotations

import asyncio
from typing import Any

from backend.infrastructure.warehouse.bridge_config import list_ros2_topics
from backend.modules.warehouse.service.live_map_readiness import (
    _ros2_workspace,
    _topic_message_text,
)
from backend.modules.warehouse.service.slam_localization_monitor import ingest_slam_status_message

SLAM_STATUS_TOPIC = "/warehouse/localization/status"


async def refresh_slam_localization_from_ros(*, timeout_s: float = 2.0) -> dict[str, Any]:
    """Probe the ROS SLAM status topic and update the in-process monitor."""
    ws = _ros2_workspace()
    try:
        topics = set(await asyncio.to_thread(list_ros2_topics, ws))
    except RuntimeError:
        return {"ingested": False, "reason": "ros_unavailable"}

    if SLAM_STATUS_TOPIC not in topics:
        return {"ingested": False, "reason": "topic_missing", "topic": SLAM_STATUS_TOPIC}

    output = await asyncio.to_thread(
        _topic_message_text,
        SLAM_STATUS_TOPIC,
        ws,
        timeout_s=max(0.5, float(timeout_s)),
    )
    if not output:
        return {"ingested": False, "reason": "no_message", "topic": SLAM_STATUS_TOPIC}

    ingest_slam_status_message(output)
    return {"ingested": True, "topic": SLAM_STATUS_TOPIC}

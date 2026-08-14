"""Warehouse live-map readiness — structure readiness."""

from __future__ import annotations

import asyncio
import logging

from backend.modules.warehouse.service.map_source_config import (
    ESDF_TOPIC_CANDIDATES,
    OCCUPANCY_TOPIC_CANDIDATES,
)

from . import deps
from .models import StructureInputReadiness
from .ros_commands import _ros2_workspace, _valid_esdf_message, _valid_occupancy_message

logger = logging.getLogger(__name__)


async def refresh_structure_input_readiness(
    *, timeout_s: float = 15.0
) -> StructureInputReadiness:
    """Perform an uncached ROS graph and first-message check for extraction inputs."""
    ws = _ros2_workspace()
    try:
        topics = await deps.list_topics_async(ws)
    except RuntimeError:
        topics = set()

    async def _first_ready(
        candidates: tuple[str, ...],
        expected_type: str,
        validator,
    ) -> tuple[str | None, str | None]:
        available = [topic for topic in candidates if topic in topics]
        if not available:
            return None, None
        deadline = asyncio.get_running_loop().time() + max(0.5, timeout_s)
        topic_info = deps.resolve("_topic_info")
        topic_message_text = deps.resolve("_topic_message_text")
        for topic in available:
            message_type = await deps.asyncio.to_thread(topic_info, topic, ws)
            if message_type != expected_type:
                continue
            remaining = max(0.5, deadline - asyncio.get_running_loop().time())
            output = await deps.asyncio.to_thread(
                topic_message_text,
                topic,
                ws,
                timeout_s=min(3.0, remaining),
            )
            if output is not None and validator(output):
                return topic, output
        return None, None

    esdf_result, occupancy_result = await asyncio.gather(
        _first_ready(
            ESDF_TOPIC_CANDIDATES,
            "sensor_msgs/msg/PointCloud2",
            _valid_esdf_message,
        ),
        _first_ready(
            OCCUPANCY_TOPIC_CANDIDATES,
            "nav_msgs/msg/OccupancyGrid",
            _valid_occupancy_message,
        ),
    )
    esdf_topic, esdf_output = esdf_result
    occupancy_topic, occupancy_output = occupancy_result
    occupancy_message: dict[str, object] | None = None
    if occupancy_output is not None:
        try:
            import yaml

            parsed = yaml.safe_load(occupancy_output)
            if isinstance(parsed, dict):
                occupancy_message = parsed
        except Exception:
            logger.debug("Could not parse live occupancy message", exc_info=True)
    return StructureInputReadiness(
        esdf_topic=esdf_topic,
        esdf_message_received=esdf_output is not None,
        esdf_message_text=esdf_output,
        occupancy_topic=occupancy_topic,
        occupancy_message_received=occupancy_output is not None,
        occupancy_message=occupancy_message,
    )

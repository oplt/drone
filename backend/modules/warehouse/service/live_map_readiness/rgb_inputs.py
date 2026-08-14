"""Warehouse live-map readiness — rgb inputs."""

from __future__ import annotations


from backend.modules.warehouse.service.map_source_config import (
    ODOM_PREFLIGHT_TOPICS,
    RGBD_INPUT_TOPICS,
)
def _rgb_inputs_ready(topics: set[str], publishing: set[str]) -> tuple[bool, list[str]]:
    missing = [topic for topic in RGBD_INPUT_TOPICS if topic not in topics]
    publishing_inputs = [topic for topic in RGBD_INPUT_TOPICS if topic in publishing]
    odom_ready = all(topic in topics for topic in ODOM_PREFLIGHT_TOPICS)
    ready = odom_ready and len(missing) == 0 and len(publishing_inputs) >= max(3, len(RGBD_INPUT_TOPICS) - 1)
    return ready, missing

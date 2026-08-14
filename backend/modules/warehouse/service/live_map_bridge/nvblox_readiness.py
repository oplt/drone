"""Warehouse live-map bridge — nvblox readiness probes."""

from __future__ import annotations

from pathlib import Path

from backend.modules.warehouse.service.nvblox_status import nvblox_status_tracker

from .ros_commands import _list_ros2_topics_safe
from .settings_helpers import _setting_str


def _esdf_topic() -> str:
    from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow

    configured = _setting_str("warehouse_esdf_topic")
    if configured:
        return configured
    flow = resolve_warehouse_bridge_flow()
    return (
        "/nvblox_node/static_esdf_pointcloud" if flow.gazebo_sim else "/warehouse/contract/map/esdf"
    )


def _nvblox_ready_from_topics(*, topics: set[str], esdf_topic: str) -> bool:
    status = nvblox_status_tracker.status()
    if status in {"live", "degraded", "warming"}:
        return status == "live"

    nvblox_status_tracker.note_topic_list(topics)
    if esdf_topic in topics:
        return True
    return any(str(topic).startswith("/nvblox_node/") for topic in topics)


def _nvblox_ready(*, ws: Path, esdf_topic: str) -> bool:
    return _nvblox_ready_from_topics(topics=_list_ros2_topics_safe(ws), esdf_topic=esdf_topic)


__all__ = ["_esdf_topic", "_nvblox_ready", "_nvblox_ready_from_topics"]

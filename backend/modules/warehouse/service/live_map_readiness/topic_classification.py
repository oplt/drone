"""Warehouse live-map readiness — topic classification."""

from __future__ import annotations


from backend.modules.warehouse.service.map_source_config import (
    NVBLOX_OPTIONAL_ESDF_TOPICS,
    NVBLOX_REQUIRED_POINTCLOUD_TOPICS,
    ODOM_PREFLIGHT_TOPICS,
    RGBD_POINTCLOUD_CANDIDATE_PREFIXES,
    RGBD_VISUALIZATION_TOPIC,
    WAREHOUSE_LIVE_MAP_SOURCES,
)
from .models import TopicTypeProbe

def _is_pointcloud2_type(message_type: str | None) -> bool:
    return bool(message_type and "sensor_msgs/msg/PointCloud2" in message_type)

def _is_voxel_block_layer_type(message_type: str | None) -> bool:
    return bool(message_type and "nvblox_msgs/msg/VoxelBlockLayer" in message_type)

def classify_topic_for_bridge(
    *,
    topic: str,
    present: bool,
    message_type: str | None,
    expect_pointcloud2: bool,
    internal_layer: bool = False,
) -> TopicTypeProbe:
    if not present:
        return TopicTypeProbe(
            topic=topic,
            present=False,
            bridge_kind="missing",
            warning=f"{topic} is missing from ROS graph",
        )

    if internal_layer and _is_voxel_block_layer_type(message_type):
        return TopicTypeProbe(
            topic=topic,
            present=True,
            message_type=message_type,
            bridge_kind="internal_layer",
            ok_for_pointcloud_bridge=False,
            info=(
                f"{topic} publishes internal nvblox layer blocks "
                f"({message_type}); use PointCloud2 export topics instead"
            ),
        )

    if expect_pointcloud2 and _is_pointcloud2_type(message_type):
        return TopicTypeProbe(
            topic=topic,
            present=True,
            message_type=message_type,
            bridge_kind="pointcloud2",
            ok_for_pointcloud_bridge=True,
        )

    if expect_pointcloud2:
        return TopicTypeProbe(
            topic=topic,
            present=True,
            message_type=message_type,
            bridge_kind="wrong_type",
            warning=(
                f"{topic} exists but type is {message_type!r}, "
                "expected sensor_msgs/msg/PointCloud2"
            ),
        )

    return TopicTypeProbe(
        topic=topic,
        present=True,
        message_type=message_type,
        bridge_kind="pointcloud2" if _is_pointcloud2_type(message_type) else "wrong_type",
        ok_for_pointcloud_bridge=_is_pointcloud2_type(message_type),
    )

def discover_rgbd_pointcloud_topics(
    topics: set[str],
    *,
    topic_types: dict[str, str | None] | None = None,
) -> list[str]:
    """Return PointCloud2 RGB-D sources, preferring the warehouse bridge topic."""
    ordered: list[str] = []
    primary = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
    if primary in topics:
        msg_type = (topic_types or {}).get(primary)
        if msg_type is None or _is_pointcloud2_type(msg_type):
            ordered.append(primary)

    for prefix in RGBD_POINTCLOUD_CANDIDATE_PREFIXES:
        for topic in sorted(topics):
            if not topic.startswith(prefix):
                continue
            msg_type = (topic_types or {}).get(topic)
            if msg_type is not None and not _is_pointcloud2_type(msg_type):
                continue
            if topic not in ordered:
                ordered.append(topic)
    return ordered

def discover_nvblox_pointcloud_topics(
    topics: set[str],
    *,
    topic_types: dict[str, str | None] | None = None,
) -> list[str]:
    discovered: list[str] = []
    for topic in (*NVBLOX_REQUIRED_POINTCLOUD_TOPICS, *NVBLOX_OPTIONAL_ESDF_TOPICS):
        if topic not in topics:
            continue
        msg_type = (topic_types or {}).get(topic)
        if msg_type is not None and not _is_pointcloud2_type(msg_type):
            continue
        discovered.append(topic)
    for topic in sorted(topics):
        if not topic.startswith("/nvblox_node/back_projected_depth/"):
            continue
        msg_type = (topic_types or {}).get(topic)
        if msg_type is not None and not _is_pointcloud2_type(msg_type):
            continue
        if topic not in discovered:
            discovered.append(topic)
    return discovered

def _rgbd_visualization_probe_topics(topics: set[str]) -> list[str]:
    """Fast readiness probes — RGB-D PointCloud2 + odom only; nvblox is optional."""
    ordered: list[str] = []
    primary = WAREHOUSE_LIVE_MAP_SOURCES["rgbd_colored"].topic
    if primary in topics:
        ordered.append(primary)
    for candidate in discover_rgbd_pointcloud_topics(topics):
        if candidate not in ordered:
            ordered.append(candidate)
    for topic in ODOM_PREFLIGHT_TOPICS:
        if topic in topics and topic not in ordered:
            ordered.append(topic)
    return ordered

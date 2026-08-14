from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.infrastructure.warehouse.bridge_config.components import bridge_probe_to_components
from backend.infrastructure.warehouse.bridge_config.constants import _raw_lidar_required
from backend.infrastructure.warehouse.bridge_config.gz_topics import list_gz_topics
from backend.infrastructure.warehouse.bridge_config.models import (
    BridgeTopicMapping,
    bridge_config_path,
    gz_to_ros_mappings,
    load_bridge_config,
)
from backend.infrastructure.warehouse.bridge_config.preflight_filters import (
    _preflight_imu,
    _preflight_lidar,
    _preflight_odometry,
    _preflight_rgbd,
    _preflight_stereo_images,
)
from backend.infrastructure.warehouse.bridge_config.publisher_probe import count_topic_publishers
from backend.infrastructure.warehouse.bridge_config.ros_env import ros_domain_id
from backend.infrastructure.warehouse.bridge_config.topic_list import (
    list_ros2_topics_with_retry,
    preflight_core_ros_topics,
)


def _topics_present(
    entries: list[BridgeTopicMapping],
    live: set[str],
    publisher_counts: dict[str, int] | None = None,
) -> bool:
    if not entries or not all(entry.ros_topic_name in live for entry in entries):
        return False
    if not publisher_counts:
        return True
    return all(publisher_counts.get(entry.ros_topic_name, 0) > 0 for entry in entries)


def probe_bridge_topics(ros2_ws: Path) -> dict[str, Any]:
    """Compare live ROS/Gazebo topic graphs against warehouse_bridge.yaml."""
    ws = ros2_ws.resolve()
    mappings = load_bridge_config(ws)
    bridged = gz_to_ros_mappings(mappings)
    core_required = preflight_core_ros_topics(ws)
    ros_topics = list_ros2_topics_with_retry(ws, required_topics=core_required)
    publisher_probe_topics = (
        core_required
        | {"/clock", "/tf"}
        | {entry.ros_topic_name for entry in _preflight_lidar(bridged)}
    )
    publisher_counts = count_topic_publishers(ws, publisher_probe_topics)
    gz_topics, gz_error = list_gz_topics()

    missing_ros = sorted(m.ros_topic_name for m in bridged if m.ros_topic_name not in ros_topics)
    missing_gz = (
        sorted(m.gz_topic_name for m in bridged if m.gz_topic_name not in gz_topics)
        if gz_error is None
        else []
    )

    odom_entries = _preflight_odometry(bridged)
    rgbd_entries = _preflight_rgbd(bridged)
    imu_entries = _preflight_imu(bridged)
    lidar_entries = _preflight_lidar(bridged)
    stereo_left_entry, stereo_right_entry = _preflight_stereo_images(bridged)

    odom_topic = odom_entries[0].ros_topic_name if odom_entries else None
    odom_ready = _topics_present(odom_entries, ros_topics, publisher_counts)
    imu_ready = _topics_present(imu_entries, ros_topics, publisher_counts)
    rgbd_ready = _topics_present(rgbd_entries, ros_topics, publisher_counts)
    lidar_ready = _topics_present(lidar_entries, ros_topics, publisher_counts)
    stereo_left_ready = (
        stereo_left_entry is not None and stereo_left_entry.ros_topic_name in ros_topics
    )
    stereo_right_ready = (
        stereo_right_entry is not None and stereo_right_entry.ros_topic_name in ros_topics
    )

    rgb_topic = rgbd_entries[0].ros_topic_name if rgbd_entries else None
    depth_topic = next(
        (m.ros_topic_name for m in rgbd_entries if m.ros_topic_name.endswith("/depth_image")),
        None,
    )
    imu_topic = imu_entries[0].ros_topic_name if imu_entries else None
    lidar_topic = lidar_entries[0].ros_topic_name if lidar_entries else None
    stereo_left_topic = stereo_left_entry.ros_topic_name if stereo_left_entry else None
    stereo_right_topic = stereo_right_entry.ros_topic_name if stereo_right_entry else None
    rgbd_imu_ok = rgbd_ready and imu_ready
    lidar_required = _raw_lidar_required()
    lidar_status = lidar_ready if lidar_required or lidar_ready else None
    ros_graph_ok = bool(ros_topics)
    preflight_core_ready = odom_ready and rgbd_imu_ok

    payload = {
        "bridge_config_path": str(bridge_config_path(ws)),
        "odometry_topic": odom_topic,
        "rgb_topic": rgb_topic,
        "depth_topic": depth_topic,
        "imu_topic": imu_topic,
        "lidar_topic": lidar_topic,
        "stereo_left_topic": stereo_left_topic,
        "stereo_right_topic": stereo_right_topic,
        "listed_ros_topics": sorted(ros_topics),
        "ros_topics": sorted(ros_topics),
        "ros_topic_count": len(ros_topics),
        "configured_ros_topics": sorted(m.ros_topic_name for m in bridged),
        "missing_configured_ros_topics": missing_ros,
        "configured_gz_topics": sorted(m.gz_topic_name for m in bridged),
        "missing_configured_gz_topics": missing_gz,
        "gz_probe_error": gz_error,
        "ros_graph_healthy": ros_graph_ok,
        "local_position_ok": odom_ready,
        "odometry_healthy": odom_ready,
        "imu_healthy": imu_ready,
        "rgb_healthy": rgbd_ready,
        "depth_healthy": rgbd_ready,
        "lidar_healthy": lidar_status,
        "stereo_left_healthy": stereo_left_ready,
        "stereo_right_healthy": stereo_right_ready,
        "tf_ok": "/tf" in ros_topics or odom_ready,
        "slam_ready": odom_ready,
        "slam_tracking_ok": odom_ready,
        "source_transport_ok": bool(set(m.ros_topic_name for m in bridged) & ros_topics),
        "rgb_depth_imu_ok": rgbd_imu_ok,
        "lidar_ok": lidar_status,
        "sensors_ok": rgbd_imu_ok,
        "preflight_core_ready": preflight_core_ready,
        "perception_stable_for_ms": 8_000 if preflight_core_ready else 0,
        "perception_required_stable_ms": 8_000,
        "ros_domain_id": ros_domain_id(),
        "publisher_counts": publisher_counts,
        "clock_publishing": publisher_counts.get("/clock", 0) > 0,
    }
    payload["components"] = bridge_probe_to_components(payload)
    return payload


CRITICAL_PROBE_TOPICS: tuple[tuple[str, str], ...] = (
    ("odometry_topic", "Local odometry topic"),
    ("imu_topic", "IMU topic"),
    ("rgb_topic", "RGB camera topic"),
    ("depth_topic", "Depth camera topic"),
)


def missing_critical_topic_blockers(overlay: dict[str, Any]) -> list[str]:
    """Human-readable blockers for yaml-critical topics absent from the ROS graph."""
    if overlay.get("preflight_core_ready") is True:
        return []
    missing = set(overlay.get("missing_configured_ros_topics") or [])
    if not missing:
        publisher_counts = overlay.get("publisher_counts") or {}
        blockers = []
        for key, label in CRITICAL_PROBE_TOPICS:
            topic = overlay.get(key)
            if topic and publisher_counts.get(topic, 0) <= 0:
                blockers.append(f"{label} is present but has no publishers: {topic}")
        return blockers
    domain = str(overlay.get("ros_domain_id") or ros_domain_id())
    suffix = (
        f"(see warehouse_bridge.yaml; ROS_DOMAIN_ID={domain}). "
        "Ensure Gazebo and the bridge are running before preflight."
    )
    blockers: list[str] = []
    for key, label in CRITICAL_PROBE_TOPICS:
        topic = overlay.get(key)
        if topic and topic in missing:
            blockers.append(f"{label} missing from ROS graph: {topic} {suffix}")
    return blockers

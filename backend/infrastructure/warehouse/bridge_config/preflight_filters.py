from __future__ import annotations

from typing import Any

from backend.infrastructure.warehouse.bridge_config.models import BridgeTopicMapping


def _preflight_odometry(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.ros_type_name == "nav_msgs/msg/Odometry"]


def _preflight_rgbd(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [
        m
        for m in mappings
        if m.ros_type_name == "sensor_msgs/msg/Image"
        and "/rgbd/" in m.ros_topic_name
        and (
            m.ros_topic_name.endswith("/image")
            or m.ros_topic_name.endswith("/depth_image")
        )
    ]


def _preflight_imu(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.ros_type_name == "sensor_msgs/msg/Imu"]


def _preflight_lidar(mappings: list[BridgeTopicMapping]) -> list[BridgeTopicMapping]:
    return [m for m in mappings if m.ros_type_name == "sensor_msgs/msg/PointCloud2"]


def _preflight_stereo_images(
    mappings: list[BridgeTopicMapping],
) -> tuple[BridgeTopicMapping | None, BridgeTopicMapping | None]:
    stereo = [
        m
        for m in mappings
        if m.ros_type_name == "sensor_msgs/msg/Image"
        and "/warehouse/stereo/" in m.ros_topic_name
        and m.ros_topic_name.endswith("/image")
    ]
    left = next((m for m in stereo if "/left/" in m.ros_topic_name), None)
    right = next((m for m in stereo if "/right/" in m.ros_topic_name), None)
    return left, right


def _topic_diag(*, topic: str | None, healthy: bool) -> dict[str, Any]:
    name = str(topic or "")
    return {
        "expected": name or None,
        "matched": name if healthy and name else None,
        "healthy": healthy,
        "readiness_state": "ok" if healthy else "missing",
    }

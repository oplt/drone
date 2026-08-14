from __future__ import annotations

from typing import Any

from backend.infrastructure.warehouse.bridge_config.constants import _raw_lidar_required
from backend.infrastructure.warehouse.bridge_config.preflight_filters import _topic_diag


def bridge_probe_to_components(overlay: dict[str, Any]) -> dict[str, Any]:
    """Map a ``probe_bridge_topics`` payload into preflight component flags."""
    ros_topics = set(overlay.get("listed_ros_topics") or overlay.get("ros_topics") or [])

    rgb_topic = str(overlay.get("rgb_topic") or "")
    depth_topic = str(overlay.get("depth_topic") or "")
    imu_topic = str(overlay.get("imu_topic") or "")
    odom_topic = str(overlay.get("odometry_topic") or "")
    lidar_topic = str(overlay.get("lidar_topic") or "")
    stereo_left = str(overlay.get("stereo_left_topic") or "")
    stereo_right = str(overlay.get("stereo_right_topic") or "")

    def _ready(flag_key: str, topic: str) -> bool:
        flag = overlay.get(flag_key)
        if flag is not None:
            return bool(flag)
        return bool(topic) and topic in ros_topics

    rgb_ok = _ready("rgb_healthy", rgb_topic)
    depth_ok = _ready("depth_healthy", depth_topic)
    imu_ok = _ready("imu_healthy", imu_topic)
    odom_ok = _ready("odometry_healthy", odom_topic) or bool(overlay.get("local_position_ok"))
    lidar_required = _raw_lidar_required()
    lidar_ok_raw = _ready("lidar_healthy", lidar_topic) or bool(overlay.get("lidar_ok"))
    lidar_ok = lidar_ok_raw if lidar_required or lidar_ok_raw else None
    stereo_left_ok = _ready("stereo_left_healthy", stereo_left)
    stereo_right_ok = _ready("stereo_right_healthy", stereo_right)
    tf_ok = bool(overlay.get("tf_ok"))
    slam_ok = bool(overlay.get("slam_ready") or overlay.get("slam_tracking_ok"))
    ros_graph_ok = bool(overlay.get("ros_graph_healthy")) or bool(ros_topics)
    rgb_depth_imu_ok = (
        bool(overlay["rgb_depth_imu_ok"])
        if overlay.get("rgb_depth_imu_ok") is not None
        else (rgb_ok and depth_ok and imu_ok)
    )
    sensors_ok = (
        bool(overlay["sensors_ok"])
        if overlay.get("sensors_ok") is not None
        else rgb_depth_imu_ok
    )
    nvblox_ok = overlay.get("nvblox_ok")

    return {
        **{
            key: value
            for key, value in overlay.items()
            if key
            not in {
                "topic_diagnostics",
            }
        },
        "ros_graph": ros_graph_ok,
        "ros2_graph": ros_graph_ok,
        "ros2_cli": ros_graph_ok,
        "camera_topics": rgb_depth_imu_ok,
        "sensors_ok": sensors_ok,
        "stereo_camera": rgb_depth_imu_ok,
        "imu_healthy": imu_ok,
        "imu": imu_ok,
        "imu_topic": imu_ok,
        "raw_lidar_healthy": lidar_ok,
        "lidar_ok": lidar_ok,
        "tf_tree": tf_ok,
        "tf": tf_ok,
        "visual_slam_healthy": slam_ok,
        "visual_slam": slam_ok,
        "vslam": slam_ok,
        "local_odometry_healthy": odom_ok,
        "local_position_ok": odom_ok,
        "odometry_healthy": odom_ok,
        "nvblox_healthy": nvblox_ok is True,
        "nvblox": nvblox_ok is True,
        "nvblox_warming_up": nvblox_ok is not True,
        "listed_topics": sorted(ros_topics),
        "odometry_topic": odom_topic or None,
        "topic_diagnostics": {
            "rgb_image": _topic_diag(topic=rgb_topic, healthy=rgb_ok),
            "depth_image": _topic_diag(topic=depth_topic, healthy=depth_ok),
            "imu": _topic_diag(topic=imu_topic, healthy=imu_ok),
            "raw_lidar": _topic_diag(topic=lidar_topic, healthy=lidar_ok is True),
            "left_image": _topic_diag(topic=stereo_left, healthy=stereo_left_ok),
            "right_image": _topic_diag(topic=stereo_right, healthy=stereo_right_ok),
            "visual_slam_odom": _topic_diag(topic=odom_topic, healthy=odom_ok),
            "local_odometry": _topic_diag(topic=odom_topic, healthy=odom_ok),
        },
    }

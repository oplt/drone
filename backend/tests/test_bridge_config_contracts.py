from __future__ import annotations

from backend.infrastructure.warehouse.bridge_config import (
    bridge_probe_to_components,
    gz_to_ros_mappings,
    missing_critical_topic_blockers,
)
from backend.infrastructure.warehouse.bridge_config.constants import GZ_TO_ROS
from backend.infrastructure.warehouse.bridge_config.models import BridgeTopicMapping


def test_gz_to_ros_mappings_filters_direction() -> None:
    mappings = [
        BridgeTopicMapping("a", "gz_a", direction=GZ_TO_ROS),
        BridgeTopicMapping("b", "gz_b", direction="ROS_TO_GZ"),
    ]

    assert [item.ros_topic_name for item in gz_to_ros_mappings(mappings)] == ["a"]


def test_bridge_probe_to_components_marks_core_sensors_ready() -> None:
    components = bridge_probe_to_components(
        {
            "listed_ros_topics": [
                "/warehouse/drone/odometry",
                "/warehouse/front/rgbd/image",
                "/warehouse/front/rgbd/depth_image",
                "/warehouse/imu",
            ],
            "odometry_topic": "/warehouse/drone/odometry",
            "rgb_topic": "/warehouse/front/rgbd/image",
            "depth_topic": "/warehouse/front/rgbd/depth_image",
            "imu_topic": "/warehouse/imu",
            "rgb_depth_imu_ok": True,
            "tf_ok": True,
            "slam_ready": True,
        }
    )

    assert components["sensors_ok"] is True
    assert components["odometry_healthy"] is True
    assert components["topic_diagnostics"]["rgb_image"]["healthy"] is True


def test_missing_critical_topic_blockers_when_preflight_core_not_ready() -> None:
    blockers = missing_critical_topic_blockers(
        {
            "preflight_core_ready": False,
            "missing_configured_ros_topics": ["/warehouse/imu"],
            "imu_topic": "/warehouse/imu",
            "ros_domain_id": "42",
        }
    )

    assert len(blockers) == 1
    assert "/warehouse/imu" in blockers[0]
    assert "ROS_DOMAIN_ID=42" in blockers[0]

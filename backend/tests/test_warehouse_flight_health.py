from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import (
    SubsystemStatus,
    check_bridge,
    check_sensors,
)


def _status(components: dict[str, Any]) -> WarehousePerceptionStatus:
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        profile="gazebo",
        bridge_url="http://127.0.0.1:8088",
        detail="ready",
        components=components,
    )


def _live_diag(topic: str, *, age_s: float = 0.01) -> dict[str, Any]:
    return {
        "expected": topic,
        "matched": topic,
        "healthy": True,
        "listed": True,
        "publishing": True,
        "publisher_count": 1,
        "last_message_age_s": age_s,
        "readiness_state": "ok_graph_presence",
    }


def test_bridge_health_uses_reported_sample_age_threshold() -> None:
    status = _status(
        {
            "ros_bridge_heartbeat": True,
            "health_sample_timestamp": time.time() - 8,
            "health_sample_max_age_ms": 20_000,
        }
    )

    health = check_bridge(status, status.components)

    assert health.status == SubsystemStatus.OK


def test_bridge_health_warns_when_sample_exceeds_reported_threshold() -> None:
    status = _status(
        {
            "ros_bridge_heartbeat": True,
            "health_sample_timestamp": time.time() - 25,
            "health_sample_max_age_ms": 20_000,
        }
    )

    health = check_bridge(status, status.components)

    assert health.status == SubsystemStatus.WARN
    assert health.message == "Bridge health sample aging"


def test_gazebo_lidar_is_optional_when_rgbd_points_capability_exists() -> None:
    components = {
        "topic_profile": "gazebo",
        "gazebo": {"sim_publishing": True},
        "topic_diagnostics": {
            "imu": _live_diag("/imu"),
            "depth": _live_diag("/warehouse/front/rgbd/depth_image"),
            "rgb_image": _live_diag("/warehouse/front/rgbd/image"),
            "visual_slam_odom": _live_diag("/warehouse/drone/odometry"),
            "raw_lidar": {
                "expected": "/scan",
                "healthy": False,
                "listed": False,
                "publishing": False,
                "publisher_count": 0,
                "readiness_state": "topic_missing",
            },
        },
        "local_odometry_state": {
            "source": "sim_odom",
            "updated_at_monotonic": time.monotonic(),
            "local_position_ok": True,
        },
    }
    config = replace(WarehouseFlightConfig.from_env(), gazebo_sim=True)

    health = check_sensors(components, config)

    assert health.status == SubsystemStatus.OK

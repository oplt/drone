from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.readiness_result import (
    readiness_from_perception_status_strict,
    topic_is_strictly_live,
    user_message_for_failure,
)
from backend.modules.warehouse.service.scan_preflight import ensure_warehouse_scan_preflight
from backend.modules.warehouse.service.takeoff_readiness import readiness_from_perception_status


def _status_with_topics(*, odom_healthy: bool, depth_healthy: bool = True) -> WarehousePerceptionStatus:
    components: dict[str, object] = {
        "ros_graph": True,
        "diagnostics_ready": True,
        "from_cache": False,
        "probe_mode": "deep_forced",
        "health_sample_timestamp": time.time(),
        "capabilities": {
            "bridge_alive": True,
            "ros_graph_ready": True,
            "can_localize": odom_healthy,
            "can_perceive_depth": depth_healthy,
            "can_perceive_rgb": True,
            "can_scan_lidar": True,
            "can_fly_warehouse_scan": odom_healthy and depth_healthy,
        },
        "topic_diagnostics": {
            "visual_slam_odom": {
                "healthy": odom_healthy,
                "publisher_count": 1 if odom_healthy else 0,
                "publishing": odom_healthy,
                "readiness_state": "ok" if odom_healthy else "no_messages",
                "expected": "/warehouse/drone/odometry",
                "matched": "/warehouse/drone/odometry",
            },
            "depth": {
                "healthy": depth_healthy,
                "publisher_count": 1 if depth_healthy else 0,
                "publishing": depth_healthy,
                "readiness_state": "ok" if depth_healthy else "topic_missing",
            },
            "rgb_image": {
                "healthy": True,
                "publisher_count": 1,
                "publishing": True,
                "readiness_state": "ok",
            },
            "imu": {
                "healthy": True,
                "publisher_count": 1,
                "publishing": True,
                "readiness_state": "ok",
            },
            "raw_lidar": {
                "healthy": True,
                "publisher_count": 1,
                "publishing": True,
                "readiness_state": "ok",
            },
        },
    }
    if odom_healthy:
        components["local_odometry_state"] = {"updated_at_monotonic": time.monotonic()}
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components=components,
    )


def test_topic_is_strictly_live_rejects_shallow_present() -> None:
    assert not topic_is_strictly_live(
        {"healthy": False, "readiness_state": "shallow_present", "listed": True}
    )


def test_strict_preflight_fails_without_odometry() -> None:
    result = readiness_from_perception_status_strict(
        _status_with_topics(odom_healthy=False),
    )
    assert result.can_fly_warehouse_scan is False
    assert result.failure_code == "odometry_topic_unavailable"
    assert "odometry" in (result.user_message or "").lower()


def test_strict_preflight_fails_without_depth() -> None:
    result = readiness_from_perception_status_strict(
        _status_with_topics(odom_healthy=True, depth_healthy=False),
    )
    assert result.can_fly_warehouse_scan is False
    assert result.failure_code == "depth_topic_unavailable"


def test_takeoff_readiness_strict_rejects_shallow_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")
    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components={
            "topic_diagnostics": {
                "visual_slam_odom": {
                    "healthy": True,
                    "readiness_state": "shallow_present",
                    "listed": True,
                    "publisher_count": 0,
                },
                "depth": {"healthy": True, "readiness_state": "shallow_present", "listed": True},
                "rgb_image": {"healthy": True, "readiness_state": "shallow_present", "listed": True},
                "imu": {"healthy": True, "readiness_state": "shallow_present", "listed": True},
                "local_odometry": {
                    "healthy": True,
                    "readiness_state": "shallow_present",
                    "listed": True,
                },
            }
        },
    )
    relaxed = readiness_from_perception_status(status, strict=False)
    strict = readiness_from_perception_status(status, strict=True)
    assert relaxed.ready is True
    assert strict.ready is False


@pytest.mark.asyncio
async def test_scan_preflight_rejects_stale_cached_health(monkeypatch: pytest.MonkeyPatch) -> None:
    cached = _status_with_topics(odom_healthy=True)
    cached.components["from_cache"] = True
    cached.components["probe_mode"] = "deep_cached"

    live = _status_with_topics(odom_healthy=True)

    port = AsyncMock()
    port.status = AsyncMock(side_effect=[cached, live, live, live])

    with patch(
        "backend.infrastructure.warehouse.perception.build_warehouse_perception_port",
        return_value=port,
    ):
        monkeypatch.setenv("WAREHOUSE_PREFLIGHT_CONSECUTIVE_CHECKS", "2")
        monkeypatch.setenv("WAREHOUSE_PREFLIGHT_CHECK_INTERVAL_S", "0.01")
        monkeypatch.setenv("WAREHOUSE_PREFLIGHT_PERCEPTION_WAIT_S", "2")
        result = await ensure_warehouse_scan_preflight(timeout_s=2.0)

    assert result.can_fly_warehouse_scan is True
    assert port.status.await_args_list[0].kwargs == {"deep": True, "force": True}


def test_user_message_for_odometry_failure() -> None:
    message = user_message_for_failure(
        "odometry_topic_unavailable",
        topic="/warehouse/drone/odometry",
    )
    assert "odometry" in message.lower()
    assert "/warehouse/drone/odometry" in message

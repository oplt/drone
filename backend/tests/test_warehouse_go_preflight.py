from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.warehouse_go_preflight import evaluate_warehouse_go_preflight


def _healthy_status(*, gazebo_publishing: bool = True) -> WarehousePerceptionStatus:
    now = time.monotonic()
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components={
            "ros_bridge_heartbeat": True,
            "ros_graph": True,
            "ros_topic_count": 24,
            "gazebo": {
                "sim_publishing": gazebo_publishing,
                "rgb_publishing": gazebo_publishing,
                "depth_publishing": gazebo_publishing,
                "odom_publishing": gazebo_publishing,
            },
            "odometry_topic": "/warehouse/drone/odometry",
            "odometry_source": "sim_odom",
            "local_odometry_state": {
                "updated_at_monotonic": now,
                "slam_tracking_ok": True,
            },
            "nvblox_deferred": True,
            "topic_diagnostics": {
                "rgb_image": {
                    "healthy": True,
                    "publishing": True,
                    "publisher_count": 1,
                    "readiness_state": "ok",
                    "last_message_age_s": 0.05,
                },
                "depth": {
                    "healthy": True,
                    "publishing": True,
                    "publisher_count": 1,
                    "readiness_state": "ok",
                    "last_message_age_s": 0.05,
                },
                "imu": {
                    "healthy": True,
                    "publishing": True,
                    "publisher_count": 1,
                    "readiness_state": "ok",
                    "last_message_age_s": 0.02,
                },
                "visual_slam_odom": {
                    "healthy": True,
                    "publishing": True,
                    "publisher_count": 1,
                    "readiness_state": "ok",
                    "last_message_age_s": 0.03,
                    "matched": "/warehouse/drone/odometry",
                },
            },
        },
    )


@pytest.mark.asyncio
async def test_go_preflight_blocks_when_gazebo_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")
    status = _healthy_status(gazebo_publishing=False)
    with patch(
        "backend.modules.warehouse.service.warehouse_go_preflight.fetch_warehouse_perception_status",
        new=AsyncMock(return_value=status),
    ), patch(
        "backend.modules.warehouse.service.warehouse_go_preflight._fetch_vehicle_runtime",
        new=AsyncMock(return_value=({}, None, False)),
    ):
        result = await evaluate_warehouse_go_preflight()
    assert result.ready_to_fly is False
    assert result.gazebo_ok is False
    assert any("Gazebo" in reason for reason in result.blocking_reasons)


@pytest.mark.asyncio
async def test_go_preflight_nvblox_deferred_at_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")
    monkeypatch.setenv("WAREHOUSE_PERCEPTION_REQUIRED_STABLE_MS", "8000")
    status = _healthy_status()
    with patch(
        "backend.modules.warehouse.service.warehouse_go_preflight.fetch_warehouse_perception_status",
        new=AsyncMock(return_value=status),
    ), patch(
        "backend.modules.warehouse.service.warehouse_go_preflight._fetch_vehicle_runtime",
        new=AsyncMock(return_value=({}, None, False)),
    ):
        result = await evaluate_warehouse_go_preflight()
    assert result.nvblox_ok is None
    assert result.categories.get("nvblox") == "DEFERRED"
    assert result.vehicle_link_ok is True
    assert result.telemetry_stream_ok is True

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from backend.infrastructure.messaging import websocket_publisher
from backend.infrastructure.messaging.websocket_publisher import TelemetryWebSocketManager
from backend.infrastructure.vehicle import mavlink_client
from backend.infrastructure.vehicle.mavlink_client import MavlinkDrone
from backend.modules.missions.service import recovery_service
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.flight_health import SubsystemHealth, SubsystemStatus
from backend.modules.warehouse.service.flight_readiness import (
    OverallReadinessStatus,
    WarehouseFlightReadiness,
)
from backend.modules.warehouse.service.flight_state_machine import (
    WarehouseFlightState,
    WarehouseFlightStateMachine,
)
from backend.modules.warehouse.service.readiness_result import (
    readiness_from_perception_status_strict,
)


def _status_with_components(components: dict[str, object]) -> WarehousePerceptionStatus:
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=False,
        status="degraded",
        profile="isaac_ros_nvblox_stereo",
        bridge_url="http://127.0.0.1:8088",
        components=components,
    )


def test_zero_topics_during_diagnostics_warming_does_not_mark_all_missing() -> None:
    result = readiness_from_perception_status_strict(
        _status_with_components(
            {
                "ros_graph": False,
                "ros_topic_count": 0,
                "probe_in_progress": True,
                "cache_ready": False,
                "warehouse_bridge_state": "starting",
                "readiness_reason": "diagnostics_cache_warming",
                "topics": {
                    "visual_slam_odom": "/warehouse/contract/odometry",
                    "depth": "/warehouse/contract/depth/image",
                    "rgb_image": "/warehouse/contract/rgb/image",
                    "imu": "/warehouse/contract/imu",
                },
                "missing_required_topics": [],
                "topic_diagnostics": {},
            }
        )
    )

    assert result.missing_required_topics == ()
    assert result.failure_code != "bridge_unreachable"


def test_no_ros_topics_with_required_topics_reports_missing() -> None:
    result = readiness_from_perception_status_strict(
        _status_with_components(
            {
                "ros_graph": False,
                "ros_topic_count": 0,
                "topics": {
                    "visual_slam_odom": "/warehouse/contract/odometry",
                    "depth": "/warehouse/contract/depth/image",
                    "rgb_image": "/warehouse/contract/rgb/image",
                    "imu": "/warehouse/contract/imu",
                },
                "missing_required_topics": [],
                "topic_diagnostics": {},
            }
        )
    )

    assert set(result.missing_required_topics) >= {
        "visual_slam_odom",
        "depth",
        "rgb_image",
        "imu",
    }
    assert result.failure_code == "ros_graph_unavailable"
    assert result.can_fly_warehouse_scan is False


def test_no_required_topics_configured_fails_closed() -> None:
    result = readiness_from_perception_status_strict(
        _status_with_components(
            {
                "ros_graph": True,
                "ros_topic_count": 3,
                "topics": {},
                "missing_required_topics": [],
                "topic_diagnostics": {},
            }
        )
    )

    assert result.failure_code == "required_topics_not_configured"
    assert result.can_fly_warehouse_scan is False


def test_topics_present_can_pass_topic_validation() -> None:
    diagnostics = {
        key: {
            "healthy": True,
            "readiness_state": "ok_via_messages",
            "publisher_count": 1,
            "publishing": True,
        }
        for key in ("visual_slam_odom", "depth", "rgb_image", "imu")
    }
    result = readiness_from_perception_status_strict(
        _status_with_components(
            {
                "ros_graph": True,
                "ros_topic_count": 4,
                "topics": {
                    "visual_slam_odom": "/warehouse/contract/odometry",
                    "depth": "/warehouse/contract/depth/image",
                    "rgb_image": "/warehouse/contract/rgb/image",
                    "imu": "/warehouse/contract/imu",
                },
                "missing_required_topics": [],
                "topic_diagnostics": diagnostics,
                "local_odometry_state": {"fresh": True, "age_s": 0.1},
            }
        )
    )

    assert result.missing_required_topics == ()
    assert result.failure_code in {None, "odometry_topic_unavailable"}


def test_state_machine_keeps_sensor_check_when_perception_degraded() -> None:
    readiness = WarehouseFlightReadiness(
        ready_to_arm=False,
        ready_to_takeoff=False,
        ready_for_autonomy=False,
        overall_status=OverallReadinessStatus.FAIL,
        subsystems={
            "bridge": SubsystemHealth(SubsystemStatus.OK, "bridge ok"),
            "autopilot": SubsystemHealth(SubsystemStatus.OK, "autopilot ok"),
            "sensors": SubsystemHealth(SubsystemStatus.FAIL, "topics missing"),
            "slam": SubsystemHealth(SubsystemStatus.FAIL, "slam missing"),
            "nvblox": SubsystemHealth(SubsystemStatus.WAITING, "waiting"),
            "planner": SubsystemHealth(SubsystemStatus.WAITING, "waiting"),
            "failsafe": SubsystemHealth(SubsystemStatus.OK, "ok"),
        },
        blocking_reasons=["topics missing"],
        updated_at=datetime.now(UTC),
    )
    machine = WarehouseFlightStateMachine(state=WarehouseFlightState.SENSOR_CHECK)

    assert machine.sync_from_readiness(readiness) == WarehouseFlightState.SENSOR_CHECK


@pytest.mark.asyncio
async def test_redis_subscriber_expected_close_is_not_error(monkeypatch) -> None:
    class FakePubSub:
        async def subscribe(self, _channel: str) -> None:
            return None

        async def listen(self):
            raise ConnectionError("Connection closed by server")
            yield {}

        async def close(self) -> None:
            return None

    class FakeRedis:
        def pubsub(self) -> FakePubSub:
            return FakePubSub()

        async def aclose(self) -> None:
            return None

    async def from_url(*_args, **_kwargs) -> FakeRedis:
        return FakeRedis()

    fake_redis_asyncio = types.SimpleNamespace(from_url=from_url)
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(asyncio=fake_redis_asyncio))
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_redis_asyncio)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        websocket_publisher,
        "logger",
        types.SimpleNamespace(
            info=lambda message, *args, **_kwargs: calls.append(("info", message % args)),
            error=lambda message, *args, **_kwargs: calls.append(("error", message % args)),
        ),
    )

    manager = TelemetryWebSocketManager()
    manager._shutting_down = True

    await manager._redis_subscriber()

    assert any("Redis subscriber closed during shutdown" in message for level, message in calls)
    assert not any(level == "error" for level, _message in calls)


@pytest.mark.asyncio
async def test_recovery_skips_when_database_unavailable(monkeypatch) -> None:
    async def unavailable() -> bool:
        return False

    monkeypatch.setattr(recovery_service, "_database_available", unavailable)
    warnings: list[str] = []
    monkeypatch.setattr(
        recovery_service,
        "logger",
        types.SimpleNamespace(warning=lambda message, *args: warnings.append(message % args)),
    )

    await recovery_service.recover_interrupted_missions(object())

    assert any("database unavailable; skipping recovery check" in item for item in warnings)


@dataclass
class _Location:
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    north: float | None = None
    east: float | None = None


class _Vehicle:
    home_location = None

    def __init__(self) -> None:
        self.location = types.SimpleNamespace(
            global_frame=_Location(lat=51.0, lon=4.0, alt=10.0),
            local_frame=_Location(north=0.0, east=0.0),
        )


def test_simulated_home_requires_sim_or_indoor_flag(monkeypatch) -> None:
    monkeypatch.setattr(mavlink_client, "connect", lambda *_args, **_kwargs: _Vehicle())
    monkeypatch.setattr(mavlink_client.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(mavlink_client.settings, "WAREHOUSE_BRIDGE_FLOW", "isaac")
    monkeypatch.delenv("SIM_MODE", raising=False)
    monkeypatch.delenv("INDOOR_NAV", raising=False)
    monkeypatch.delenv("WAREHOUSE_GAZEBO_SIM", raising=False)

    with pytest.raises(RuntimeError, match="GPS home is required"):
        MavlinkDrone("udp:127.0.0.1:14550", heartbeat_timeout=1).connect()


def test_simulated_home_allowed_in_explicit_sim_mode(monkeypatch) -> None:
    monkeypatch.setattr(mavlink_client, "connect", lambda *_args, **_kwargs: _Vehicle())
    monkeypatch.setattr(mavlink_client.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(mavlink_client.settings, "WAREHOUSE_BRIDGE_FLOW", "isaac")
    monkeypatch.setenv("SIM_MODE", "true")

    drone = MavlinkDrone("udp:127.0.0.1:14550", heartbeat_timeout=1)
    drone.connect()

    assert drone.home_source == "simulated_home"

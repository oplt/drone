from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.exceptions import WarehouseFlightNotReadyError
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import (
    SubsystemStatus,
    check_autopilot,
    check_bridge,
    check_failsafe,
    check_nvblox,
    check_planner,
    check_sensors,
    check_slam,
)
from backend.modules.warehouse.service.flight_readiness import (
    SlamStabilityTracker,
    compute_warehouse_flight_readiness,
    evaluate_subsystems_from_components,
)
from backend.modules.warehouse.service.perception_stability import PerceptionStabilityTracker
from backend.modules.warehouse.service.flight_state_machine import (
    WarehouseFlightState,
    WarehouseFlightStateMachine,
)
from backend.modules.warehouse.service.flight_watchdog import WarehouseFlightWatchdog


def _healthy_components(*, slam_tracking_ok: bool = True) -> dict[str, object]:
    now = time.monotonic()
    return {
        "ros_bridge_heartbeat": True,
        "health_sample_timestamp": time.time(),
        "local_odometry_state": {
            "updated_at_monotonic": now,
            "slam_tracking_ok": slam_tracking_ok,
            "localization_confidence": 0.9,
        },
        "slam_tracking_ok": slam_tracking_ok,
        "nvblox_healthy": True,
        "nvblox": True,
        "nvblox_fps": 10.0,
        "obstacle_distance_m": 3.0,
        "topic_diagnostics": {
            "imu": {
                "healthy": True,
                "readiness_state": "ok",
                "publisher_count": 1,
                "publishing": True,
                "last_message_age_s": 0.02,
            },
            "depth": {
                "healthy": True,
                "readiness_state": "ok",
                "publisher_count": 1,
                "publishing": True,
                "last_message_age_s": 0.05,
            },
            "rgb_image": {
                "healthy": True,
                "readiness_state": "ok",
                "publisher_count": 1,
                "publishing": True,
                "last_message_age_s": 0.08,
            },
            "visual_slam_odom": {
                "healthy": True,
                "readiness_state": "ok",
                "publisher_count": 1,
                "publishing": True,
                "last_message_age_s": 0.03,
            },
        },
    }


def _status(*, reachable: bool = True) -> WarehousePerceptionStatus:
    return WarehousePerceptionStatus(
        configured=True,
        reachable=reachable,
        ready=True,
        status="ready",
        components=_healthy_components(),
    )


def test_sensors_fail_when_gazebo_idle() -> None:
    components = _healthy_components()
    components["gazebo"] = {
        "sim_publishing": False,
        "rgb_publishing": False,
        "depth_publishing": False,
        "odom_publishing": False,
        "rgb_topic": "/warehouse/front/rgbd/image",
    }
    health = check_sensors(
        components,
        WarehouseFlightConfig(gazebo_sim=True, require_gazebo_publishing=True),
    )
    assert health.status == SubsystemStatus.FAIL
    assert "Gazebo sensors idle" in health.message


def test_sensors_ok_when_gazebo_publishing() -> None:
    components = _healthy_components()
    components["gazebo"] = {
        "sim_publishing": True,
        "rgb_publishing": True,
        "depth_publishing": True,
        "odom_publishing": True,
    }
    health = check_sensors(
        components,
        WarehouseFlightConfig(gazebo_sim=True, require_gazebo_publishing=True),
    )
    assert health.status == SubsystemStatus.OK


def test_bridge_fail_when_unreachable() -> None:
    status = _status(reachable=False)
    health = check_bridge(status, {})
    assert health.status == SubsystemStatus.FAIL


def test_autopilot_ok_with_fresh_heartbeat() -> None:
    telemetry = Telemetry(
        lat=0.0,
        lon=0.0,
        alt=1.0,
        heading=0.0,
        groundspeed=0.0,
        mode="GUIDED",
        battery_remaining=80.0,
        heartbeat_age_s=0.05,
        is_armable=True,
    )
    health = check_autopilot(
        telemetry=telemetry,
        components={},
        config=WarehouseFlightConfig(min_battery_percent=30.0),
    )
    assert health.status == SubsystemStatus.OK


def test_autopilot_fail_low_battery() -> None:
    telemetry = Telemetry(
        lat=0.0,
        lon=0.0,
        alt=1.0,
        heading=0.0,
        groundspeed=0.0,
        mode="GUIDED",
        battery_remaining=20.0,
        heartbeat_age_s=0.05,
        is_armable=True,
    )
    health = check_autopilot(
        telemetry=telemetry,
        components={},
        config=WarehouseFlightConfig(min_battery_percent=30.0),
    )
    assert health.status == SubsystemStatus.FAIL


def test_sensors_fail_when_depth_missing() -> None:
    components = _healthy_components()
    components["topic_diagnostics"] = dict(components["topic_diagnostics"])  # type: ignore[arg-type]
    del components["topic_diagnostics"]["depth"]  # type: ignore[index]
    health = check_sensors(components, WarehouseFlightConfig())
    assert health.status == SubsystemStatus.FAIL


def test_sensors_fail_when_odometry_unreadable() -> None:
    components = _healthy_components()
    components["odometry_state_unreadable"] = True
    components["odometry_topic"] = "/warehouse/drone/odometry"
    components["odometry_source"] = "sim_odom"
    health = check_sensors(components, WarehouseFlightConfig(gazebo_sim=True))
    assert health.status == SubsystemStatus.FAIL
    assert "unreadable" in health.message.lower()
    assert "sim_odom" in health.message


def test_check_slam_tracking_lost_includes_stable_for_ms() -> None:
    components = _healthy_components()
    components["slam_tracking_ok"] = False
    health = check_slam(components, WarehouseFlightConfig(), stable_for_ms=1200)
    assert health.status == SubsystemStatus.FAIL
    assert health.details.get("stable_for_ms") == 1200


def test_slam_ok_when_tracking_live() -> None:
    config = WarehouseFlightConfig()
    health = check_slam(_healthy_components(), config, stable_for_ms=0)
    assert health.status == SubsystemStatus.OK


def test_slam_stability_tracker_accumulates() -> None:
    tracker = SlamStabilityTracker()
    assert tracker.stable_for_ms(slam_ok=True) >= 0
    time.sleep(0.05)
    stable_ms = tracker.stable_for_ms(slam_ok=True)
    assert stable_ms >= 40
    tracker.stable_for_ms(slam_ok=False)
    assert tracker.stable_for_ms(slam_ok=True) == 0


def test_nvblox_fail_when_inactive() -> None:
    components = _healthy_components()
    components["nvblox_healthy"] = False
    components["nvblox_checks_active"] = True
    health = check_nvblox(
        components,
        WarehouseFlightConfig(),
        mapping_stack_running=True,
    )
    assert health.status == SubsystemStatus.FAIL


def test_nvblox_waiting_when_mapping_stack_idle() -> None:
    components = _healthy_components()
    components["nvblox_deferred"] = True
    components["nvblox_healthy"] = False
    health = check_nvblox(
        components,
        WarehouseFlightConfig(),
        mapping_stack_running=False,
    )
    assert health.status == SubsystemStatus.WAITING
    assert "flight start" in health.message.lower()


def test_planner_waiting_without_mission() -> None:
    health = check_planner(
        mission_loaded=False,
        mission_valid=False,
        speed_mps=None,
        altitude_m=None,
        config=WarehouseFlightConfig(),
    )
    assert health.status == SubsystemStatus.WAITING


def test_ready_for_autonomy_blocked_without_stability() -> None:
    config = WarehouseFlightConfig(perception_required_stable_ms=8000)
    tracker = PerceptionStabilityTracker()
    readiness = compute_warehouse_flight_readiness(
        bridge=check_bridge(_status(), _healthy_components()),
        autopilot=check_autopilot(
            telemetry=Telemetry(
                lat=0,
                lon=0,
                alt=1,
                heading=0,
                groundspeed=0,
                mode="GUIDED",
                battery_remaining=90,
                heartbeat_age_s=0.01,
                is_armable=True,
            ),
            components={},
            config=config,
        ),
        sensors=check_sensors(_healthy_components(), config),
        slam=check_slam(_healthy_components(), config),
        nvblox=check_nvblox(_healthy_components(), config),
        planner=check_planner(
            mission_loaded=True,
            mission_valid=True,
            speed_mps=0.8,
            altitude_m=2.0,
            config=config,
        ),
        failsafe=check_failsafe(),
        config=config,
        stable_for_ms=6000,
        perception_stable_for_ms=tracker.stable_for_ms(
            perception_ok=True,
        ),
    )
    assert readiness.ready_to_arm is True
    assert readiness.ready_for_autonomy is False
    assert any("stable" in reason.lower() for reason in readiness.blocking_reasons)


def test_ready_to_arm_requires_bridge_and_autopilot() -> None:
    config = WarehouseFlightConfig(perception_required_stable_ms=8000)
    readiness = compute_warehouse_flight_readiness(
        bridge=check_bridge(_status(), _healthy_components()),
        autopilot=check_autopilot(
            telemetry=Telemetry(
                lat=0,
                lon=0,
                alt=1,
                heading=0,
                groundspeed=0,
                mode="GUIDED",
                battery_remaining=90,
                heartbeat_age_s=0.01,
                is_armable=True,
            ),
            components={},
            config=config,
        ),
        sensors=check_sensors(_healthy_components(), config),
        slam=check_slam(_healthy_components(), config, stable_for_ms=6000),
        nvblox=check_nvblox(_healthy_components(), config),
        planner=check_planner(
            mission_loaded=True,
            mission_valid=True,
            speed_mps=0.8,
            altitude_m=2.0,
            config=config,
        ),
        failsafe=check_failsafe(),
        config=config,
        stable_for_ms=6000,
        perception_stable_for_ms=8000,
        mapping_stack_running=True,
    )
    assert readiness.ready_to_arm is True
    assert readiness.ready_to_takeoff is True
    assert readiness.ready_for_autonomy is True


def test_ready_for_autonomy_blocked_without_mission() -> None:
    config = WarehouseFlightConfig()
    tracker = SlamStabilityTracker()
    for _ in range(3):
        tracker.stable_for_ms(slam_ok=True)
        time.sleep(0.02)
    stable_ms = tracker.stable_for_ms(slam_ok=True)
    readiness = evaluate_subsystems_from_components(
        status=_status(),
        components=_healthy_components(),
        telemetry=Telemetry(
            lat=0,
            lon=0,
            alt=1,
            heading=0,
            groundspeed=0,
            mode="GUIDED",
            battery_remaining=90,
            heartbeat_age_s=0.01,
            is_armable=True,
        ),
        config=config,
        mission_loaded=False,
        mission_valid=False,
        stability_tracker=tracker,
    )
    assert readiness.ready_to_arm is True
    assert readiness.ready_for_autonomy is False
    assert any("mission" in reason.lower() for reason in readiness.blocking_reasons)


def test_state_machine_progresses_with_readiness() -> None:
    machine = WarehouseFlightStateMachine()
    machine.reset()
    readiness = evaluate_subsystems_from_components(
        status=_status(),
        components=_healthy_components(),
        telemetry=None,
        config=WarehouseFlightConfig(gazebo_sim=True),
        mission_loaded=True,
        mission_valid=True,
        stability_tracker=SlamStabilityTracker(),
    )
    state = machine.sync_from_readiness(readiness)
    assert state in {
        WarehouseFlightState.LOCALIZATION_CHECK,
        WarehouseFlightState.MAPPING_CHECK,
        WarehouseFlightState.ARM_READY,
        WarehouseFlightState.MISSION_READY,
        WarehouseFlightState.SYSTEM_CHECK,
        WarehouseFlightState.SENSOR_CHECK,
    }


def test_watchdog_triggers_on_bridge_loss() -> None:
    watchdog = WarehouseFlightWatchdog()
    watchdog.start()
    action = watchdog.evaluate(
        components={"ros_bridge_heartbeat": False},
        status=_status(reachable=False),
    )
    assert action.triggered is True
    assert action.action == "land"


def test_ready_to_takeoff_without_nvblox_when_stack_idle() -> None:
    config = WarehouseFlightConfig(perception_required_stable_ms=8000)
    components = _healthy_components()
    components["nvblox_deferred"] = True
    components["nvblox_healthy"] = False
    readiness = compute_warehouse_flight_readiness(
        bridge=check_bridge(_status(), components),
        autopilot=check_autopilot(
            telemetry=Telemetry(
                lat=0,
                lon=0,
                alt=1,
                heading=0,
                groundspeed=0,
                mode="GUIDED",
                battery_remaining=90,
                heartbeat_age_s=0.01,
                is_armable=True,
            ),
            components={},
            config=config,
        ),
        sensors=check_sensors(components, config),
        slam=check_slam(components, config, stable_for_ms=6000),
        nvblox=check_nvblox(components, config, mapping_stack_running=False),
        planner=check_planner(
            mission_loaded=True,
            mission_valid=True,
            speed_mps=0.8,
            altitude_m=2.0,
            config=config,
        ),
        failsafe=check_failsafe(),
        config=config,
        stable_for_ms=6000,
        perception_stable_for_ms=8000,
        mapping_stack_running=False,
    )
    assert readiness.ready_to_takeoff is True
    assert readiness.ready_for_autonomy is False


@pytest.mark.asyncio
async def test_assert_ready_raises_when_not_autonomy_ready() -> None:
    from backend.modules.warehouse.service.flight_service import (
        WarehouseFlightMissionContext,
        assert_ready_for_warehouse_flight_start,
    )

    status = _status()
    with patch(
        "backend.modules.warehouse.service.flight_service.fetch_warehouse_perception_status",
        new=AsyncMock(return_value=status),
    ), patch(
        "backend.modules.warehouse.service.flight_service._fetch_autopilot_telemetry",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.modules.warehouse.service.flight_service._mapping_stack_running",
        new=AsyncMock(return_value=False),
    ):
        with pytest.raises(WarehouseFlightNotReadyError) as exc:
            await assert_ready_for_warehouse_flight_start(
                mission=WarehouseFlightMissionContext(loaded=True, valid=True),
            )
        assert exc.value.blocking_reasons

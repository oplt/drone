from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.preflight.checks.schemas import CheckStatus, PreflightReport
from backend.modules.preflight.checks.service import PreflightOrchestrator
from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.warehouse_preflight import (
    build_warehouse_vehicle_state_from_perception,
    run_warehouse_ros_preflight_report,
    uses_warehouse_ros_preflight,
)


def _healthy_perception_status() -> WarehousePerceptionStatus:
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        profile="gazebo",
        bridge_url="http://127.0.0.1:8088",
        components={
            "ros_graph": True,
            "camera_topics": True,
            "imu_healthy": True,
            "visual_slam_healthy": True,
            "local_odometry_healthy": True,
            "raw_lidar_healthy": True,
            "nvblox_healthy": True,
            "tf_tree": True,
            "stereo_sync": True,
            "missing_required_topics": [],
            "missing_nvblox_topics": [],
            "local_odometry_state": {
                "local_north_m": 1.0,
                "local_east_m": 2.0,
                "local_down_m": -1.5,
                "slam_tracking_ok": True,
                "odometry_drift_m": 0.1,
            },
            "topic_diagnostics": {
                "rgb_image": {"healthy": True, "readiness_state": "ok_graph_presence"},
                "depth": {"healthy": True},
                "imu": {"healthy": True},
                "visual_slam_odom": {"healthy": True},
                "raw_lidar": {"healthy": True},
                "pointcloud": {"healthy": True},
            },
        },
    )


def test_uses_warehouse_ros_preflight() -> None:
    assert uses_warehouse_ros_preflight("warehouse_scan") is True
    assert uses_warehouse_ros_preflight("indoor_exploration") is True
    assert uses_warehouse_ros_preflight("grid") is False


def test_build_warehouse_vehicle_state_without_mavlink() -> None:
    state = build_warehouse_vehicle_state_from_perception(_healthy_perception_status())
    assert state.local_position_ok is True
    assert state.odometry_healthy is True
    assert state.mode == "GUIDED"


@pytest.mark.asyncio
async def test_run_warehouse_ros_preflight_does_not_call_mavlink_telemetry() -> None:
    report = PreflightReport(
        mission_type="warehouse_scan",
        overall_status=CheckStatus.PASS,
        base_checks=[],
        mission_checks=[],
        summary={"passed": 1, "failed": 0, "warned": 0, "skipped": 0, "total_checks": 1},
        timestamp=0.0,
    )
    mission_data = {"type": "warehouse_scan", "waypoints": [], "speed": 1.0, "altitude_agl": 2.5}

    with (
        patch(
            "backend.modules.warehouse.service.warehouse_preflight.fetch_warehouse_perception_status",
            new_callable=AsyncMock,
            return_value=_healthy_perception_status(),
        ),
        patch.object(PreflightOrchestrator, "run", new_callable=AsyncMock, return_value=report) as run_mock,
    ):
        result = await run_warehouse_ros_preflight_report(mission_data, cruise_alt=2.5)

    assert result.overall_status == CheckStatus.PASS
    run_mock.assert_awaited_once()
    vehicle_state = run_mock.await_args.args[0]
    assert isinstance(vehicle_state, Telemetry)


@pytest.mark.asyncio
async def test_recovery_preflight_warehouse_skips_get_telemetry() -> None:
    from backend.modules.vehicle_runtime.recovery_service import RuntimeRecoveryServiceMixin

    report = PreflightReport(
        mission_type="warehouse_scan",
        overall_status=CheckStatus.PASS,
        base_checks=[],
        mission_checks=[],
        summary={"passed": 1, "failed": 0, "warned": 0, "skipped": 0, "total_checks": 1},
        timestamp=0.0,
    )
    mixin = RuntimeRecoveryServiceMixin()
    mixin.drone = MagicMock()
    mixin.drone.get_telemetry = MagicMock(side_effect=RuntimeError("Vehicle not connected yet"))
    mixin._flight_id = "flight_test"
    mixin.mqtt = None

    mission_data = {"type": "warehouse_scan", "waypoints": [], "speed": 1.0, "altitude_agl": 2.5}

    with patch(
        "backend.modules.warehouse.service.warehouse_preflight.run_warehouse_ros_preflight_report",
        new_callable=AsyncMock,
        return_value=report,
    ) as warehouse_run:
        result = await mixin._run_preflight_checks(
            [],
            2.5,
            raise_on_fail=False,
            mission_data=mission_data,
        )

    assert result.overall_status == CheckStatus.PASS
    warehouse_run.assert_awaited_once()
    mixin.drone.get_telemetry.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_preflight_grid_requires_mavlink_telemetry() -> None:
    from backend.modules.vehicle_runtime.recovery_service import RuntimeRecoveryServiceMixin

    mixin = RuntimeRecoveryServiceMixin()
    mixin.drone = MagicMock()
    mixin.drone.get_telemetry = MagicMock(side_effect=RuntimeError("Vehicle not connected yet"))
    mixin._flight_id = None
    mixin.mqtt = None

    mission_data = {"type": "grid", "waypoints": [], "speed": 5.0, "altitude_agl": 30.0}

    with pytest.raises(RuntimeError, match="Vehicle not connected"):
        await mixin._run_preflight_checks(
            [],
            30.0,
            raise_on_fail=False,
            mission_data=mission_data,
        )

    mixin.drone.get_telemetry.assert_called()


@pytest.mark.asyncio
async def test_warehouse_ros_base_checker_skips_mavlink_gates() -> None:
    from backend.modules.preflight.checks.context import PreflightContext
    from backend.modules.preflight.checks.warehouse_scan_base import (
        WarehouseRosBasePreflightChecks,
    )
    from backend.modules.missions.schemas.mission_types import create_mission_from_dict

    vehicle_state = build_warehouse_vehicle_state_from_perception(_healthy_perception_status())
    mission = create_mission_from_dict(
        {
            "type": "warehouse_scan",
            "waypoints": [],
            "local_polygon": [
                {"x_m": 0.0, "y_m": 0.0},
                {"x_m": 10.0, "y_m": 0.0},
                {"x_m": 10.0, "y_m": 10.0},
            ],
            "scan_layers": [{"layer_index": 0, "label": "L1", "z_m": 2.5}],
            "corridor_spacing_m": 3.0,
            "clearance_m": 0.6,
        }
    )
    context = PreflightContext(
        vehicle_state=vehicle_state,
        mission=mission,
        config_overrides={
            "WAREHOUSE_PERCEPTION_STATUS": _healthy_perception_status().model_dump(
                mode="python"
            ),
        },
    )
    checker = WarehouseRosBasePreflightChecks(context)
    results = await checker.run(gps_timeout_s=0.0)

    names = {result.name for result in results}
    assert "Warehouse ROS Position" in names
    assert "Warehouse ROS Odometry" in names
    assert "Heartbeat Age" not in names


def test_warehouse_overall_status_ignores_non_critical_fail() -> None:
    from backend.modules.preflight.checks.schemas import CheckResult, CheckStatus
    from backend.modules.preflight.checks.service import PreflightOrchestrator

    orchestrator = PreflightOrchestrator()
    orchestrator.critical_base_checks = ["Warehouse ROS Odometry"]
    orchestrator.critical_mission_checks = ["Warehouse ROS Bridge"]
    results = [
        CheckResult(name="Warehouse ROS Odometry", status=CheckStatus.PASS, message="ok"),
        CheckResult(name="Warehouse ROS Bridge", status=CheckStatus.PASS, message="ok"),
        CheckResult(
            name="Warehouse Stereo Sync",
            status=CheckStatus.FAIL,
            message="missing from payload",
        ),
        CheckResult(
            name="Warehouse Nvblox",
            status=CheckStatus.WARN,
            message="not started yet",
        ),
    ]
    overall = orchestrator._warehouse_overall_status("warehouse_scan", results)
    assert overall == CheckStatus.WARN


def test_nvblox_preflight_warn_when_not_started_in_gazebo_sim(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.modules.preflight.checks.context import PreflightContext
    from backend.modules.preflight.checks.mission_specific import WarehouseScanMissionPreflight
    from backend.modules.missions.schemas.mission_types import create_mission_from_dict

    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")
    monkeypatch.delenv("WAREHOUSE_PREFLIGHT_WAIT_NVBLOX", raising=False)

    status = _healthy_perception_status()
    status = status.model_copy(
        update={
            "ready": True,
            "components": {
                **status.components,
                "nvblox_healthy": False,
                "missing_nvblox_topics": ["pointcloud", "mesh"],
                "listed_topics": ["/warehouse/front/rgbd/image", "/imu"],
            },
        }
    )
    mission = create_mission_from_dict(
        {
            "type": "warehouse_scan",
            "waypoints": [],
            "local_polygon": [
                {"x_m": 0.0, "y_m": 0.0},
                {"x_m": 10.0, "y_m": 0.0},
                {"x_m": 10.0, "y_m": 10.0},
            ],
            "scan_layers": [{"layer_index": 0, "label": "L1", "z_m": 2.5}],
            "corridor_spacing_m": 3.0,
            "clearance_m": 0.6,
        }
    )
    context = PreflightContext(
        vehicle_state=build_warehouse_vehicle_state_from_perception(status),
        mission=mission,
        config_overrides={
            "WAREHOUSE_PERCEPTION_STATUS": status.model_dump(mode="python"),
        },
    )
    checker = WarehouseScanMissionPreflight(context)
    result = checker.check_nvblox()

    assert result.status == CheckStatus.WARN
    assert "starts when the warehouse flight begins" in result.message

from __future__ import annotations

import time

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import SubsystemStatus
from backend.modules.warehouse.service.warehouse_vehicle_checks import (
    check_telemetry_stream,
    check_vehicle_battery,
    check_vehicle_link,
    vehicle_runtime_from_parts,
)


def test_vehicle_link_requires_connection_outside_sim() -> None:
    config = WarehouseFlightConfig(gazebo_sim=False)
    runtime = vehicle_runtime_from_parts(
        drone_connected=False,
        runtime_snapshot={"running": False, "source_connected": False, "last_update": 0.0},
        autopilot=None,
    )
    result = check_vehicle_link(runtime=runtime, config=config, sim_ros_fallback=False)
    assert result.status == SubsystemStatus.FAIL


def test_telemetry_stream_ok_when_recent() -> None:
    config = WarehouseFlightConfig(gazebo_sim=False)
    runtime = vehicle_runtime_from_parts(
        drone_connected=True,
        runtime_snapshot={
            "running": True,
            "source_connected": True,
            "last_update": time.time(),
        },
        autopilot=None,
    )
    result = check_telemetry_stream(runtime=runtime, config=config, sim_ros_fallback=False)
    assert result.status == SubsystemStatus.OK


def test_battery_blocks_below_minimum() -> None:
    config = WarehouseFlightConfig(gazebo_sim=False, min_battery_percent=30.0)
    autopilot = Telemetry(
        lat=0.0,
        lon=0.0,
        alt=0.0,
        heading=0.0,
        groundspeed=0.0,
        mode="GUIDED",
        battery_remaining=20.0,
    )
    result = check_vehicle_battery(autopilot=autopilot, config=config)
    assert result.status == SubsystemStatus.FAIL

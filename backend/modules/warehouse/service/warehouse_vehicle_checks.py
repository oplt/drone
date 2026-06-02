from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import SubsystemHealth, SubsystemStatus
from backend.modules.warehouse.service.runtime_safety import odometry_state_is_fresh


@dataclass(frozen=True)
class WarehouseVehicleRuntime:
    drone_connected: bool
    telemetry_running: bool
    telemetry_source_connected: bool
    telemetry_last_update: float
    autopilot: Telemetry | None


def check_vehicle_link(
    *,
    runtime: WarehouseVehicleRuntime,
    config: WarehouseFlightConfig,
    sim_ros_fallback: bool,
) -> SubsystemHealth:
    if runtime.drone_connected:
        return SubsystemHealth(
            SubsystemStatus.OK,
            "Vehicle connected to orchestrator",
        )
    if config.gazebo_sim and sim_ros_fallback:
        return SubsystemHealth(
            SubsystemStatus.OK,
            "Gazebo sim: ROS odometry substituting vehicle link",
            details={"sim_mode": True},
        )
    return SubsystemHealth(
        SubsystemStatus.FAIL,
        "No active vehicle connection detected",
        details={"hint": "Connect drone telemetry before warehouse flight"},
    )


def check_telemetry_stream(
    *,
    runtime: WarehouseVehicleRuntime,
    config: WarehouseFlightConfig,
    sim_ros_fallback: bool,
    recent_threshold_sec: float = 15.0,
) -> SubsystemHealth:
    if (
        runtime.telemetry_running
        and runtime.telemetry_source_connected
        and runtime.telemetry_last_update > 0
    ):
        age_s = max(0.0, time.time() - runtime.telemetry_last_update)
        if age_s <= recent_threshold_sec:
            return SubsystemHealth(
                SubsystemStatus.OK,
                f"MAVLink telemetry stream live ({age_s:.1f}s ago)",
                last_seen_ms=int(age_s * 1000.0),
            )
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            f"Telemetry updates stale ({age_s:.1f}s / {recent_threshold_sec:.0f}s)",
            last_seen_ms=int(age_s * 1000.0),
        )

    if config.gazebo_sim and sim_ros_fallback:
        return SubsystemHealth(
            SubsystemStatus.OK,
            "Gazebo sim: ROS odometry substituting MAVLink telemetry stream",
            details={"sim_mode": True},
        )

    if not runtime.telemetry_running:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Telemetry runtime is not running",
            details={"hint": "Connect drone telemetry before warehouse flight"},
        )
    if not runtime.telemetry_source_connected:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Telemetry runtime up, but drone data source disconnected",
        )
    return SubsystemHealth(
        SubsystemStatus.FAIL,
        "No telemetry updates received yet",
    )


def check_vehicle_battery(
    *,
    autopilot: Telemetry | None,
    config: WarehouseFlightConfig,
) -> SubsystemHealth:
    battery = autopilot.battery_remaining if autopilot is not None else None
    if battery is None:
        if config.gazebo_sim:
            return SubsystemHealth(
                SubsystemStatus.OK,
                "Gazebo sim: battery not exposed (assumed full)",
                details={"sim_mode": True},
            )
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "Battery percentage not exposed by telemetry",
            details={"min_battery_percent": config.min_battery_percent},
        )
    if battery < config.min_battery_percent:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            f"Battery below minimum ({battery:.0f}% < {config.min_battery_percent:.0f}%)",
            details={"battery_percent": battery},
        )
    if battery < config.min_battery_percent + 10:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            f"Battery low ({battery:.0f}%)",
            details={"battery_percent": battery},
        )
    return SubsystemHealth(
        SubsystemStatus.OK,
        f"Battery OK ({battery:.0f}%)",
        details={"battery_percent": battery},
    )


def sim_ros_odometry_fallback_ok(
    components: dict[str, Any],
    *,
    config: WarehouseFlightConfig,
) -> bool:
    if not config.gazebo_sim:
        return False
    if components.get("odometry_state_unreadable"):
        return False
    if (
        components.get("visual_slam_healthy")
        or components.get("visual_slam")
        or components.get("local_odometry_healthy")
        or components.get("odometry_fresh")
    ):
        return True
    odom = components.get("local_odometry_state")
    odom_dict = odom if isinstance(odom, dict) else {}
    return odometry_state_is_fresh(
        odom_dict,
        max_age_s=config.odometry_max_age_s,
    )


def vehicle_runtime_from_parts(
    *,
    drone_connected: bool,
    runtime_snapshot: dict[str, Any],
    autopilot: Telemetry | None,
) -> WarehouseVehicleRuntime:
    last_update_raw = runtime_snapshot.get("last_update", 0.0)
    last_update = float(last_update_raw) if isinstance(last_update_raw, (int, float)) else 0.0
    return WarehouseVehicleRuntime(
        drone_connected=drone_connected,
        telemetry_running=bool(runtime_snapshot.get("running")),
        telemetry_source_connected=bool(runtime_snapshot.get("source_connected")),
        telemetry_last_update=last_update,
        autopilot=autopilot,
    )

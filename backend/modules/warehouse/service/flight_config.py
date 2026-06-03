from __future__ import annotations

import os
from dataclasses import dataclass

from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WarehouseFlightConfig:
    imu_max_age_ms: int = 50
    pose_max_age_ms: int = 100
    odometry_max_age_s: float = 2.0
    depth_max_age_ms: int = 200
    rgb_max_age_ms: int = 500
    costmap_max_age_ms: int = 500
    slam_required_stable_ms: int = 5000
    perception_required_stable_ms: int = 8000
    min_battery_percent: float = 30.0
    max_command_latency_ms: int = 150
    takeoff_clear_radius_m: float = 1.5
    max_indoor_speed_mps: float = 1.0
    max_indoor_altitude_m: float = 6.0
    require_nvblox_for_autonomy: bool = True
    require_mission_for_autonomy: bool = True
    require_gazebo_publishing: bool = True
    gazebo_sim: bool = False
    require_mavlink_for_flight: bool = True

    @classmethod
    def from_env(cls) -> WarehouseFlightConfig:
        gazebo_flow = resolve_warehouse_bridge_flow().name == "gazebo"
        default_perception_stable_ms = 5000 if gazebo_flow else 8000
        return cls(
            imu_max_age_ms=_int_env("WAREHOUSE_IMU_MAX_AGE_MS", 50),
            pose_max_age_ms=_int_env("WAREHOUSE_POSE_MAX_AGE_MS", 100),
            odometry_max_age_s=_float_env("WAREHOUSE_ODOMETRY_MAX_AGE_S", 2.0),
            depth_max_age_ms=_int_env("WAREHOUSE_DEPTH_MAX_AGE_MS", 200),
            rgb_max_age_ms=_int_env("WAREHOUSE_RGB_MAX_AGE_MS", 500),
            costmap_max_age_ms=_int_env("WAREHOUSE_COSTMAP_MAX_AGE_MS", 500),
            slam_required_stable_ms=_int_env("WAREHOUSE_SLAM_REQUIRED_STABLE_MS", 5000),
            perception_required_stable_ms=_int_env(
                "WAREHOUSE_PERCEPTION_REQUIRED_STABLE_MS",
                default_perception_stable_ms,
            ),
            min_battery_percent=_float_env("WAREHOUSE_MIN_BATTERY_PERCENT", 30.0),
            max_command_latency_ms=_int_env("WAREHOUSE_MAX_COMMAND_LATENCY_MS", 150),
            takeoff_clear_radius_m=_float_env("WAREHOUSE_TAKEOFF_CLEAR_RADIUS_M", 1.5),
            max_indoor_speed_mps=_float_env("WAREHOUSE_MAX_INDOOR_SPEED_MPS", 1.0),
            max_indoor_altitude_m=_float_env("WAREHOUSE_MAX_INDOOR_ALTITUDE_M", 6.0),
            require_nvblox_for_autonomy=_bool_env("WAREHOUSE_TAKEOFF_REQUIRE_NVBLOX", True),
            require_mission_for_autonomy=True,
            require_gazebo_publishing=_bool_env("WAREHOUSE_GAZEBO_REQUIRE_PUBLISHING", True),
            gazebo_sim=gazebo_flow,
            require_mavlink_for_flight=_bool_env("WAREHOUSE_FLIGHT_REQUIRE_MAVLINK", True),
        )

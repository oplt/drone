from __future__ import annotations

import logging
import os
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.preflight.checks.schemas import PreflightReport
from backend.modules.preflight.checks.service import PreflightOrchestrator
from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.ports import WarehousePerceptionStatus
import math

from backend.modules.warehouse.service.bridge_stack_lifecycle import (
    ensure_warehouse_bridge_stack_for_preflight,
)

logger = logging.getLogger(__name__)

WAREHOUSE_ROS_PREFLIGHT_MISSION_TYPES = frozenset(
    {
        MissionType.WAREHOUSE_SCAN.value,
        MissionType.INDOOR_EXPLORATION.value,
    }
)

def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _bool_flag(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def uses_warehouse_ros_preflight(mission_type: str | MissionType | None) -> bool:
    if mission_type is None:
        return False
    if isinstance(mission_type, MissionType):
        return mission_type in {
            MissionType.WAREHOUSE_SCAN,
            MissionType.INDOOR_EXPLORATION,
        }
    return str(mission_type).strip().lower() in WAREHOUSE_ROS_PREFLIGHT_MISSION_TYPES


def _components_from_status(
    status: WarehousePerceptionStatus | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(status, WarehousePerceptionStatus):
        raw = status.components
        return raw if isinstance(raw, dict) else {}
    components = status.get("components")
    return components if isinstance(components, dict) else {}


def _odometry_state(components: dict[str, Any]) -> dict[str, Any]:
    raw = components.get("local_odometry_state")
    return raw if isinstance(raw, dict) else {}


def perception_status_to_dict(
    status: WarehousePerceptionStatus,
) -> dict[str, Any]:
    return status.model_dump(mode="python")


def build_warehouse_vehicle_state_from_perception(
        status: WarehousePerceptionStatus | dict[str, Any],
) -> Telemetry:
    components = _components_from_status(status)
    odom = _odometry_state(components)

    north = _float_or_none(odom.get("local_north_m"))
    east = _float_or_none(odom.get("local_east_m"))
    down = _float_or_none(odom.get("local_down_m"))

    numeric_local_pose = north is not None and east is not None and down is not None

    local_position_ok = bool(
        _bool_flag(components.get("local_odometry_healthy"))
        or _bool_flag(components.get("local_position_ok"))
        or numeric_local_pose
    )

    vslam_ok = bool(
        _bool_flag(components.get("visual_slam_healthy"))
        or _bool_flag(components.get("visual_slam"))
        or _bool_flag(components.get("vslam"))
    )

    raw_lidar_ok = _bool_flag(components.get("raw_lidar_healthy"))

    depth_ok = (
        components.get("depth")
        if isinstance(components.get("depth"), bool)
        else _bool_flag(components.get("depth_healthy"))
    )

    drift = _float_or_none(odom.get("odometry_drift_m"))
    if drift is None:
        drift = _float_or_none(components.get("odometry_drift_m"))

    alt_m = -down if down is not None else 0.0

    sim_mode = os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return Telemetry(
        lat=0.0,
        lon=0.0,
        alt=alt_m,
        heading=_float_or_none(odom.get("yaw_deg")) or 0.0,
        groundspeed=0.0,
        mode="GUIDED",
        battery_remaining=100.0 if sim_mode else None,
        gps_fix_type=0,
        hdop=99.0,
        satellites_visible=0,
        heartbeat_age_s=0.0,
        is_armable=True,
        home_set=True,
        home_lat=0.0,
        home_lon=0.0,
        ekf_ok=vslam_ok or local_position_ok,
        local_north_m=north,
        local_east_m=east,
        local_down_m=down,
        local_position_ok=local_position_ok,
        local_origin_ok=local_position_ok,
        odometry_healthy=vslam_ok or local_position_ok,
        odometry_drift_m=drift,
        lidar_healthy=raw_lidar_ok,
        estimator_ready=vslam_ok or local_position_ok,
        rangefinder_healthy=bool(depth_ok),
        slam_ready=vslam_ok,
        slam_tracking_ok=_bool_flag(odom.get("slam_tracking_ok")) or vslam_ok,
        localization_confidence=_float_or_none(odom.get("localization_confidence")),
        obstacle_distance_m=_float_or_none(components.get("obstacle_distance_m")),
        ceiling_distance_m=_float_or_none(components.get("ceiling_distance_m")),
    )



async def fetch_warehouse_perception_status(
    *,
    deep: bool = True,
    force: bool = False,
) -> WarehousePerceptionStatus:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    return await build_warehouse_perception_port().status(deep=deep, force=force)


def warehouse_perception_config_overrides(
    status: WarehousePerceptionStatus,
) -> dict[str, object]:
    return {"WAREHOUSE_PERCEPTION_STATUS": perception_status_to_dict(status)}


async def run_warehouse_ros_preflight_report(
        mission_data: dict[str, Any],
        *,
        cruise_alt: float,
        flight_id: str | None = None,
        preflight_config: dict[str, Any] | None = None,
        **kwargs: Any,
) -> PreflightReport:
    """Run preflight using ROS bridge health — never calls MAVLink get_telemetry."""

    await ensure_warehouse_bridge_stack_for_preflight()

    status = await fetch_warehouse_perception_status(deep=True, force=True)
    vehicle_state = build_warehouse_vehicle_state_from_perception(status)

    config_overrides = dict(kwargs.pop("config_overrides", {}) or {})
    config_overrides.update(warehouse_perception_config_overrides(status))
    config_overrides.setdefault("CRUISE_ALT_M", cruise_alt)

    runtime_preflight = {
        "ENFORCE_PREFLIGHT_RANGE": settings.enforce_preflight_range,
        "HDOP_MAX": settings.HDOP_MAX,
        "SAT_MIN": settings.SAT_MIN,
        "HOME_MAX_DIST": settings.HOME_MAX_DIST,
        "GPS_FIX_TYPE_MIN": settings.GPS_FIX_TYPE_MIN,
        "EKF_THRESHOLD": settings.EKF_THRESHOLD,
        "COMPASS_HEALTH_REQUIRED": settings.COMPASS_HEALTH_REQUIRED,
        "BATTERY_MIN_V": settings.BATTERY_MIN_V,
        "BATTERY_MIN_PERCENT": settings.BATTERY_MIN_PERCENT,
        "BATTERY_RESERVE_PCT": settings.BATTERY_MIN_PERCENT,
        "HEARTBEAT_MAX_AGE": settings.HEARTBEAT_MAX_AGE,
        "MSG_RATE_MIN_HZ": settings.MSG_RATE_MIN_HZ,
        "RTL_MIN_ALT": settings.RTL_MIN_ALT,
        "MIN_CLEARANCE": settings.MIN_CLEARANCE,
        "MIN_CLEARANCE_M": settings.MIN_CLEARANCE,
        "AGL_MIN": settings.AGL_MIN,
        "AGL_MAX": settings.AGL_MAX,
        "MAX_RANGE_M": settings.MAX_RANGE_M,
        "MAX_WAYPOINTS": settings.MAX_WAYPOINTS,
        "NFZ_BUFFER_M": settings.NFZ_BUFFER_M,
        "A_LAT_MAX": settings.A_LAT_MAX,
        "BANK_MAX_DEG": settings.BANK_MAX_DEG,
        "TURN_PENALTY_S": settings.TURN_PENALTY_S,
        "WP_RADIUS_M": settings.WP_RADIUS_M,
    }
    for key, value in runtime_preflight.items():
        config_overrides.setdefault(key, value)

    orchestrator = PreflightOrchestrator(config=preflight_config or {})
    mission_type = str(mission_data.get("type") or "").lower()
    logger.info(
        "Running warehouse ROS preflight mission_type=%s bridge_ready=%s reachable=%s",
        mission_type,
        status.ready,
        status.reachable,
    )

    return await orchestrator.run(
        vehicle_state,
        mission_data,
        flight_id=str(flight_id) if flight_id is not None else None,
        allowed_modes=["STANDBY", "GUIDED", "AUTO", "LOITER"],
        config_overrides=config_overrides,
        gps_timeout_s=0.0,
        **kwargs,
    )

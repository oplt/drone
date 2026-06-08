from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.warehouse.bridge_config import bridge_probe_to_components
from backend.modules.missions.schemas.mission_types import MissionType, SIM_WAREHOUSE_LOCAL_ORIGIN
from backend.modules.preflight.checks.schemas import CheckStatus, PreflightReport
from backend.modules.preflight.checks.service import PreflightOrchestrator
from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.ports import WarehousePerceptionStatus

logger = logging.getLogger(__name__)

WAREHOUSE_ROS_PREFLIGHT_MISSION_TYPES = frozenset(
    {
        MissionType.WAREHOUSE_SCAN.value,
        MissionType.INDOOR_EXPLORATION.value,
    }
)


def uses_warehouse_ros_preflight(mission_type: str | MissionType | None) -> bool:
    if mission_type is None:
        return False
    if isinstance(mission_type, MissionType):
        return mission_type in {
            MissionType.WAREHOUSE_SCAN,
            MissionType.INDOOR_EXPLORATION,
        }
    return str(mission_type).strip().lower() in WAREHOUSE_ROS_PREFLIGHT_MISSION_TYPES


def default_warehouse_scan_preflight_mission_data(*, cruise_alt: float = 2.0) -> dict[str, Any]:
    """Minimal warehouse_scan payload for UI preflight (matches mission-start checks)."""
    return {
        "type": MissionType.WAREHOUSE_SCAN.value,
        "speed": 0.8,
        "altitude_agl": float(cruise_alt),
        "waypoints": [],
        "local_polygon": [
            {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0},
            {"x_m": 10.0, "y_m": 0.0, "z_m": 0.0},
            {"x_m": 10.0, "y_m": 10.0, "z_m": 0.0},
        ],
        "local_origin": SIM_WAREHOUSE_LOCAL_ORIGIN.model_dump(mode="python"),
        "control_mode": "local_setpoint",
        "local_control_mode": "local_setpoint",
    }


def warehouse_preflight_failed_checks(report: PreflightReport) -> list[str]:
    return [
        result.name
        for result in report.base_checks + report.mission_checks
        if result.status == CheckStatus.FAIL
    ]


def warehouse_preflight_can_start(report: PreflightReport) -> bool:
    from backend.modules.preflight.checks.profiles.warehouse_scan import (
        WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS,
        WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS,
    )

    if report.overall_status == CheckStatus.FAIL:
        return False
    critical = set(WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS) | set(
        WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS
    )
    for result in report.base_checks + report.mission_checks:
        if result.name in critical and result.status == CheckStatus.FAIL:
            return False
    return True


_CHECK_CATEGORY_MAP: dict[str, str] = {
    "Warehouse ROS Position": "odometry",
    "Warehouse ROS Odometry": "odometry",
    "Warehouse Local Position": "localization",
    "Warehouse Local Odometry": "localization",
    "Warehouse ROS Bridge": "bridge",
    "Warehouse ROS Graph": "bridge",
    "Warehouse Camera Topics": "rgb_depth_imu",
    "Warehouse IMU Topic": "sensors",
    "Warehouse Visual SLAM": "localization",
    "Warehouse LiDAR": "lidar",
    "Warehouse TF Tree": "tf",
    "Warehouse Nvblox": "nvblox",
}


def apply_ros_preflight_gate(
    categories: dict[str, str],
    blockers: list[str],
    *,
    report: PreflightReport,
) -> tuple[bool, list[str], list[str]]:
    """Merge orchestrator preflight results into UI snapshot; returns ready flag + blockers."""
    from backend.modules.preflight.checks.profiles.indoor_warehouse import (
        INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS,
        INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS,
    )
    from backend.modules.preflight.checks.profiles.warehouse_scan import (
        WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS,
        WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS,
    )

    critical = set(WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS) | set(
        WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS
    ) | set(INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS) | set(
        INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS
    )
    failed_names = warehouse_preflight_failed_checks(report)
    merged_blockers = list(blockers)
    for result in report.base_checks + report.mission_checks:
        if result.status != CheckStatus.FAIL:
            continue
        if result.name not in critical:
            continue
        label = result.name
        if result.message:
            label = f"{result.name}: {result.message}"
        if label not in merged_blockers:
            merged_blockers.append(label)
        category = _CHECK_CATEGORY_MAP.get(result.name)
        if category is not None:
            categories[category] = "FAIL"
    can_start = warehouse_preflight_can_start(report)
    return can_start, merged_blockers, failed_names


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


def perception_status_to_dict(status: WarehousePerceptionStatus) -> dict[str, Any]:
    return status.model_dump(mode="python")


def warehouse_perception_config_overrides(
    status: WarehousePerceptionStatus,
) -> dict[str, object]:
    return {"WAREHOUSE_PERCEPTION_STATUS": perception_status_to_dict(status)}


def _merge_probe_components(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    probe_components = overlay.get("components")
    if isinstance(probe_components, dict):
        merged.update(probe_components)
    elif overlay:
        merged.update(bridge_probe_to_components(overlay))
    return merged


def build_warehouse_vehicle_state_from_perception(
    status: WarehousePerceptionStatus | dict[str, Any],
) -> Telemetry:
    components = (
        status.components
        if isinstance(status, WarehousePerceptionStatus)
        else status.get("components") if isinstance(status.get("components"), dict) else {}
    )
    odom = components.get("local_odometry_state")
    odom = odom if isinstance(odom, dict) else {}

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
    odometry_healthy = vslam_ok or local_position_ok
    if odometry_healthy and drift is None:
        drift = 0.0
    alt_m = -down if down is not None else 0.0

    from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow

    sim_mode = resolve_warehouse_bridge_flow().gazebo_sim
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
        odometry_healthy=odometry_healthy,
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
    from backend.infrastructure.warehouse.bridge_config import probe_bridge_topics
    from backend.modules.warehouse.api import _ensure_ros_bridge_running, _ros2_workspace

    if deep or force:
        await _ensure_ros_bridge_running(start=True)

    status = await build_warehouse_perception_port().status(deep=deep, force=force)
    ws = _ros2_workspace()
    overlay: dict[str, Any] = {}
    if ws.exists() and (deep or force):
        try:
            overlay = await asyncio.to_thread(probe_bridge_topics, ws)
        except Exception as exc:
            logger.warning("Warehouse ROS topic probe failed during preflight: %s", exc)

    components = _merge_probe_components(dict(status.components or {}), overlay)

    ros_topics = set(overlay.get("listed_ros_topics") or components.get("listed_topics") or [])
    reachable = bool(
        status.reachable
        or overlay.get("ros_graph_healthy")
        or overlay.get("local_position_ok")
        or ros_topics
    )
    ready = bool(
        overlay.get("preflight_core_ready")
        or (
            reachable
            and (
                overlay.get("local_position_ok")
                or overlay.get("slam_ready")
                or components.get("local_position_ok")
                or components.get("visual_slam_healthy")
            )
        )
    )
    detail = status.detail
    if overlay.get("gz_probe_error") and detail:
        detail = f"{detail}; {overlay['gz_probe_error']}"
    elif overlay.get("gz_probe_error"):
        detail = str(overlay["gz_probe_error"])

    return WarehousePerceptionStatus(
        configured=bool(status.configured or ws.exists()),
        reachable=reachable,
        ready=ready,
        status="ready" if ready else ("configured" if reachable else "unavailable"),
        profile=status.profile,
        bridge_flow=status.bridge_flow,
        bridge_url=status.bridge_url,
        websocket_url=status.websocket_url,
        capture_root=status.capture_root,
        detail=detail,
        components=components,
    )


async def run_warehouse_ros_preflight_report(
    mission_data: dict[str, Any],
    *,
    cruise_alt: float,
    flight_id: str | None = None,
    preflight_config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> PreflightReport:
    """Run warehouse mission preflight from ROS bridge health, not MAVLink telemetry."""

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

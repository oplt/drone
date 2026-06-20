from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
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
        str(MissionType.WAREHOUSE_SCAN.value).strip().lower(),
        str(MissionType.INDOOR_EXPLORATION.value).strip().lower(),
    }
)

_TRUE_STRINGS = {"1", "true", "yes", "on", "y", "t"}
_FALSE_STRINGS = {"0", "false", "no", "off", "n", "f", ""}


def _setting(name: str, default: object = None) -> object:
    return getattr(settings, name, default)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_float(value: object, default: float) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else default


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return bool(value)
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if lowered in _TRUE_STRINGS:
        return True
    if lowered in _FALSE_STRINGS:
        return False
    return None


def _bool_flag(value: object) -> bool:
    return _bool_or_none(value) is True


def _any_true(*values: object) -> bool:
    return any(_bool_or_none(value) is True for value in values)


def _any_false(*values: object) -> bool:
    return any(_bool_or_none(value) is False for value in values)


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
    altitude = max(0.1, _safe_float(cruise_alt, 2.0))
    return {
        "type": MissionType.WAREHOUSE_SCAN.value,
        "speed": 0.8,
        "altitude_agl": altitude,
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
        for result in (*report.base_checks, *report.mission_checks)
        if result.status == CheckStatus.FAIL
    ]


def _critical_check_names() -> set[str]:
    critical: set[str] = set()
    try:
        from backend.modules.preflight.checks.profiles.warehouse_scan import (
            WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS,
            WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS,
        )

        critical.update(WAREHOUSE_SCAN_CRITICAL_BASE_CHECKS)
        critical.update(WAREHOUSE_SCAN_CRITICAL_MISSION_CHECKS)
    except Exception:
        logger.debug("Warehouse scan critical check profile unavailable", exc_info=True)
    try:
        from backend.modules.preflight.checks.profiles.indoor_warehouse import (
            INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS,
            INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS,
        )

        critical.update(INDOOR_WAREHOUSE_CRITICAL_BASE_CHECKS)
        critical.update(INDOOR_WAREHOUSE_CRITICAL_MISSION_CHECKS)
    except Exception:
        logger.debug("Indoor warehouse critical check profile unavailable", exc_info=True)
    return critical


def warehouse_preflight_can_start(report: PreflightReport) -> bool:
    if report.overall_status == CheckStatus.FAIL:
        return False
    critical = _critical_check_names()
    for result in (*report.base_checks, *report.mission_checks):
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
    critical = _critical_check_names()
    failed_names = warehouse_preflight_failed_checks(report)
    merged_blockers = list(blockers)
    for result in (*report.base_checks, *report.mission_checks):
        if result.status != CheckStatus.FAIL or result.name not in critical:
            continue
        label = result.name
        if getattr(result, "message", None):
            label = f"{result.name}: {result.message}"
        if label not in merged_blockers:
            merged_blockers.append(label)
        category = _CHECK_CATEGORY_MAP.get(result.name)
        if category is not None:
            categories[category] = "FAIL"
    can_start = warehouse_preflight_can_start(report)
    return can_start, merged_blockers, failed_names


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
    if overlay:
        try:
            converted = bridge_probe_to_components(overlay)
        except Exception:
            logger.debug("Failed to convert ROS bridge probe to components", exc_info=True)
            converted = {}
        if isinstance(converted, dict):
            merged.update(converted)
        for key in (
            "listed_ros_topics",
            "listed_topics",
            "ros_graph_healthy",
            "preflight_core_ready",
            "local_position_ok",
            "slam_ready",
            "gz_probe_error",
        ):
            if key in overlay:
                merged[key] = overlay[key]
    probe_components = overlay.get("components") if isinstance(overlay, dict) else None
    if isinstance(probe_components, dict):
        merged.update(probe_components)
    return merged


def _components_from_status(status: WarehousePerceptionStatus | dict[str, Any]) -> dict[str, Any]:
    if isinstance(status, WarehousePerceptionStatus):
        raw = status.components
    elif isinstance(status, dict):
        raw = status.get("components")
    else:
        raw = None
    return dict(raw) if isinstance(raw, dict) else {}


def build_warehouse_vehicle_state_from_perception(
    status: WarehousePerceptionStatus | dict[str, Any],
) -> Telemetry:
    components = _components_from_status(status)
    odom = components.get("local_odometry_state")
    odom = odom if isinstance(odom, dict) else {}

    north = _float_or_none(odom.get("local_north_m"))
    east = _float_or_none(odom.get("local_east_m"))
    down = _float_or_none(odom.get("local_down_m"))
    numeric_local_pose = north is not None and east is not None and down is not None

    explicit_local_unhealthy = _any_false(
        components.get("local_odometry_healthy"),
        components.get("local_position_ok"),
        odom.get("local_odometry_healthy"),
        odom.get("local_position_ok"),
    )
    local_position_ok = False if explicit_local_unhealthy else bool(
        _any_true(components.get("local_odometry_healthy"), components.get("local_position_ok"))
        or numeric_local_pose
    )

    vslam_ok = False if _any_false(
        components.get("visual_slam_healthy"),
        components.get("visual_slam"),
        components.get("vslam"),
        odom.get("slam_tracking_ok"),
    ) else _any_true(
        components.get("visual_slam_healthy"),
        components.get("visual_slam"),
        components.get("vslam"),
    )

    raw_lidar_component = components.get("raw_lidar_healthy")
    raw_lidar_ok = _bool_or_none(raw_lidar_component)
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

    try:
        from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow

        sim_mode = resolve_warehouse_bridge_flow().gazebo_sim
    except Exception:
        sim_mode = False

    slam_tracking = _bool_or_none(odom.get("slam_tracking_ok"))
    if slam_tracking is None:
        slam_tracking = vslam_ok

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
        slam_tracking_ok=bool(slam_tracking),
        localization_confidence=_float_or_none(odom.get("localization_confidence")),
        obstacle_distance_m=_float_or_none(components.get("obstacle_distance_m")),
        ceiling_distance_m=_float_or_none(components.get("ceiling_distance_m")),
    )


# Short-lived cache + single-flight guard for the (expensive) ROS perception
# probe. The UI polls preflight every ~15s and the mission-start path runs it
# too; without coalescing, overlapping calls each spawn a `ros2 topic list`
# subprocess + deep bridge probe. The TTL absorbs burst duplicates; the lock
# collapses concurrent callers onto one probe. The readiness wait-loop passes
# bypass_cache=True so it never reads stale data on the critical path.
_PERCEPTION_PROBE_LOCK = asyncio.Lock()
_perception_status_cache: WarehousePerceptionStatus | None = None
_perception_status_cache_at: float = 0.0


def _perception_status_ttl_s() -> float:
    return max(0.0, _safe_float(_setting("warehouse_perception_status_cache_ttl_s", 2.5), 2.5))


async def fetch_warehouse_perception_status(
    *,
    deep: bool = True,
    force: bool = False,
    bypass_cache: bool = False,
) -> WarehousePerceptionStatus:
    global _perception_status_cache, _perception_status_cache_at

    ttl = 0.0 if bypass_cache else _perception_status_ttl_s()

    if ttl > 0.0 and _perception_status_cache is not None:
        age = time.monotonic() - _perception_status_cache_at
        if age < ttl:
            return _perception_status_cache

    async with _PERCEPTION_PROBE_LOCK:
        # Re-check after acquiring: a concurrent caller may have just refreshed
        # it, so overlapping requests share a single probe instead of stacking.
        if ttl > 0.0 and _perception_status_cache is not None:
            age = time.monotonic() - _perception_status_cache_at
            if age < ttl:
                return _perception_status_cache

        status = await _probe_warehouse_perception_status(deep=deep, force=force)
        _perception_status_cache = status
        _perception_status_cache_at = time.monotonic()
        return status


async def _probe_warehouse_perception_status(
    *,
    deep: bool = True,
    force: bool = False,
) -> WarehousePerceptionStatus:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port
    from backend.infrastructure.warehouse.bridge_config import probe_bridge_topics
    from backend.modules.warehouse.ros_bridge_runtime import ensure_ros_bridge_running, ros2_workspace

    bridge_start_error: str | None = None
    if deep or force:
        try:
            await ensure_ros_bridge_running(start=True)
        except Exception as exc:
            bridge_start_error = str(exc)
            logger.warning("Warehouse ROS bridge start/check failed: %s", exc)

    status = await build_warehouse_perception_port().status(deep=deep, force=force)
    ws = ros2_workspace()
    overlay: dict[str, Any] = {}
    if ws.exists() and (deep or force):
        try:
            overlay = await asyncio.to_thread(probe_bridge_topics, ws)
        except Exception as exc:
            logger.warning("Warehouse ROS topic probe failed during preflight: %s", exc)

    components = _merge_probe_components(dict(status.components or {}), overlay)

    ros_topics = set(
        str(topic)
        for topic in (
            overlay.get("listed_ros_topics")
            or overlay.get("listed_topics")
            or components.get("listed_topics")
            or []
        )
    )
    reachable = bool(
        _bool_flag(getattr(status, "reachable", False))
        or _bool_flag(overlay.get("ros_graph_healthy"))
        or _bool_flag(overlay.get("local_position_ok"))
        or bool(ros_topics)
    )
    ready = bool(
        _bool_flag(overlay.get("preflight_core_ready"))
        or (
            reachable
            and (
                _bool_flag(overlay.get("local_position_ok"))
                or _bool_flag(overlay.get("slam_ready"))
                or _bool_flag(components.get("local_position_ok"))
                or _bool_flag(components.get("visual_slam_healthy"))
            )
        )
    )
    detail_parts = [str(part) for part in (getattr(status, "detail", None), overlay.get("gz_probe_error"), bridge_start_error) if part]
    detail = "; ".join(dict.fromkeys(detail_parts)) or None

    return WarehousePerceptionStatus(
        configured=bool(getattr(status, "configured", False) or ws.exists()),
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


def _warm_mapping_stack_in_background() -> None:
    """Kick off nvblox + RGB-D + live-map graph warm-up when preflight starts.

    A1 made the mapping stack reusable; S1/R2 extend warm-up so nvblox init,
    RGB-D readiness polling, and bridge topic probes overlap preflight/arming
    instead of blocking the pre-takeoff critical path.
    """
    if not _bool_flag(_setting("warehouse_preflight_warm_nvblox", True)):
        return
    try:
        from backend.modules.warehouse.service.mapping_stack_lifecycle import (
            _is_mapping_stack_process_running,
            _maybe_start_mapping_stack_cmd,
        )
    except Exception:
        logger.debug("nvblox warm-up unavailable", exc_info=True)
        return
    if _is_mapping_stack_process_running():
        # Stack already warm; still refresh RGB-D / topic probes in background.
        _schedule_mapping_warm_followups(skip_nvblox_start=True)
        return

    async def _warm() -> None:
        try:
            await _maybe_start_mapping_stack_cmd()
        except Exception:
            logger.debug("Background nvblox warm-up failed", exc_info=True)
        await _run_mapping_warm_followups()

    _schedule_async_warm_task(_warm)


def _schedule_async_warm_task(coro_factory) -> None:
    with contextlib.suppress(RuntimeError):
        asyncio.get_running_loop().create_task(coro_factory())


async def _run_mapping_warm_followups() -> None:
    from backend.modules.warehouse.service.live_map_readiness import (
        warm_live_map_ros_graph,
        warm_rgbd_readiness_background,
    )

    try:
        await warm_live_map_ros_graph()
    except Exception:
        logger.debug("Live-map ROS graph warm-up failed", exc_info=True)
    if _bool_flag(_setting("warehouse_preflight_warm_rgbd", True)):
        try:
            await warm_rgbd_readiness_background()
        except Exception:
            logger.debug("Background RGB-D warm-up failed", exc_info=True)


def _schedule_mapping_warm_followups(*, skip_nvblox_start: bool) -> None:
    del skip_nvblox_start

    async def _followups() -> None:
        await _run_mapping_warm_followups()

    _schedule_async_warm_task(_followups)


# Cache full orchestrator preflight reports for UI polling (not mission-start).
_PREFLIGHT_REPORT_LOCK = asyncio.Lock()
_preflight_report_cache_key: str | None = None
_preflight_report_cache: PreflightReport | None = None
_preflight_report_cache_at: float = 0.0


def _preflight_report_cache_ttl_s() -> float:
    return max(0.0, _safe_float(_setting("warehouse_preflight_report_cache_ttl_s", 4.0), 4.0))


def _preflight_report_key(mission_data: dict[str, Any], cruise_alt: float) -> str:
    mission_type = str(mission_data.get("type") or "").strip().lower()
    return f"{mission_type}:{max(0.1, _safe_float(cruise_alt, 2.0)):.2f}"


async def run_warehouse_ros_preflight_report(
    mission_data: dict[str, Any],
    *,
    cruise_alt: float,
    perception_status: WarehousePerceptionStatus | None = None,
    flight_id: str | None = None,
    preflight_config: dict[str, Any] | None = None,
    force: bool = False,
    source: str = "unknown",
    **kwargs: Any,
) -> PreflightReport:
    """Run warehouse mission preflight from ROS bridge health, not MAVLink telemetry."""

    global _preflight_report_cache_key, _preflight_report_cache, _preflight_report_cache_at

    cache_key = _preflight_report_key(mission_data, cruise_alt)
    ttl = 0.0 if force else _preflight_report_cache_ttl_s()
    if ttl > 0.0 and _preflight_report_cache is not None and _preflight_report_cache_key == cache_key:
        if (time.monotonic() - _preflight_report_cache_at) < ttl:
            try:
                from backend.observability.prometheus_metrics import (
                    warehouse_preflight_cache_serves_total,
                )

                warehouse_preflight_cache_serves_total.labels(state="ros_report_hit").inc()
            except Exception:
                pass
            return _preflight_report_cache

    async with _PREFLIGHT_REPORT_LOCK:
        if ttl > 0.0 and _preflight_report_cache is not None and _preflight_report_cache_key == cache_key:
            if (time.monotonic() - _preflight_report_cache_at) < ttl:
                try:
                    from backend.observability.prometheus_metrics import (
                        warehouse_preflight_cache_serves_total,
                    )

                    warehouse_preflight_cache_serves_total.labels(state="ros_report_hit").inc()
                except Exception:
                    pass
                return _preflight_report_cache

        _warm_mapping_stack_in_background()

        status = perception_status
        if status is None:
            status = await fetch_warehouse_perception_status(deep=True, force=force)
        vehicle_state = build_warehouse_vehicle_state_from_perception(status)

        config_overrides = dict(kwargs.pop("config_overrides", {}) or {})
        config_overrides.update(warehouse_perception_config_overrides(status))
        config_overrides.setdefault("CRUISE_ALT_M", max(0.1, _safe_float(cruise_alt, 2.0)))

        runtime_preflight = {
            "ENFORCE_PREFLIGHT_RANGE": _setting("enforce_preflight_range"),
            "HDOP_MAX": _setting("HDOP_MAX"),
            "SAT_MIN": _setting("SAT_MIN"),
            "HOME_MAX_DIST": _setting("HOME_MAX_DIST"),
            "GPS_FIX_TYPE_MIN": _setting("GPS_FIX_TYPE_MIN"),
            "EKF_THRESHOLD": _setting("EKF_THRESHOLD"),
            "COMPASS_HEALTH_REQUIRED": _setting("COMPASS_HEALTH_REQUIRED"),
            "BATTERY_MIN_V": _setting("BATTERY_MIN_V"),
            "BATTERY_MIN_PERCENT": _setting("BATTERY_MIN_PERCENT"),
            "BATTERY_RESERVE_PCT": _setting("BATTERY_MIN_PERCENT"),
            "HEARTBEAT_MAX_AGE": _setting("HEARTBEAT_MAX_AGE"),
            "MSG_RATE_MIN_HZ": _setting("MSG_RATE_MIN_HZ"),
            "RTL_MIN_ALT": _setting("RTL_MIN_ALT"),
            "MIN_CLEARANCE": _setting("MIN_CLEARANCE"),
            "MIN_CLEARANCE_M": _setting("MIN_CLEARANCE"),
            "AGL_MIN": _setting("AGL_MIN"),
            "AGL_MAX": _setting("AGL_MAX"),
            "MAX_RANGE_M": _setting("MAX_RANGE_M"),
            "MAX_WAYPOINTS": _setting("MAX_WAYPOINTS"),
            "NFZ_BUFFER_M": _setting("NFZ_BUFFER_M"),
            "A_LAT_MAX": _setting("A_LAT_MAX"),
            "BANK_MAX_DEG": _setting("BANK_MAX_DEG"),
            "TURN_PENALTY_S": _setting("TURN_PENALTY_S"),
            "WP_RADIUS_M": _setting("WP_RADIUS_M"),
        }
        for key, value in runtime_preflight.items():
            if value is not None:
                config_overrides.setdefault(key, value)

        orchestrator = PreflightOrchestrator(config=preflight_config or {})
        mission_type = str(mission_data.get("type") or "").lower()
        logger.info(
            "Running warehouse ROS preflight source=%s mission_type=%s bridge_ready=%s reachable=%s",
            str(source or "unknown"),
            mission_type,
            status.ready,
            status.reachable,
        )

        report = await orchestrator.run(
            vehicle_state,
            mission_data,
            flight_id=str(flight_id) if flight_id is not None else None,
            allowed_modes=["STANDBY", "GUIDED", "AUTO", "LOITER"],
            config_overrides=config_overrides,
            gps_timeout_s=0.0,
            **kwargs,
        )
        _preflight_report_cache_key = cache_key
        _preflight_report_cache = report
        _preflight_report_cache_at = time.monotonic()
        return report

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.infrastructure.warehouse.bridge_config import (
    missing_critical_topic_blockers,
    ros_command_env,
)
from backend.modules.organizations.service import can_access_org_scope
from backend.modules.vehicle_runtime.factory import build_orchestrator
from backend.modules.warehouse.http_access import repo
from backend.modules.warehouse.http_models import WarehousePreflightOut
from backend.modules.warehouse.ros_bridge_runtime import ensure_ros_bridge_running, ros2_workspace
from backend.modules.warehouse.service.warehouse_preflight import (
    apply_ros_preflight_gate,
    default_warehouse_scan_preflight_mission_data,
    fetch_warehouse_perception_status,
    run_warehouse_ros_preflight_report,
)

logger = logging.getLogger(__name__)
_preflight_drone_lock = asyncio.Lock()


def _status(ok: bool | None, *, required: bool = True) -> str:
    if ok is True:
        return "OK"
    if ok is False:
        return "FAIL" if required else "WARN"
    return "UNKNOWN" if required else "DEFERRED"


def _read_odometry_overlay_sync() -> tuple[dict[str, Any], str | None]:
    path_raw = str(getattr(settings, "WAREHOUSE_ODOMETRY_STATE_PATH", "") or "").strip()
    if not path_raw:
        return {}, "WAREHOUSE_ODOMETRY_STATE_PATH is not configured."
    path = Path(path_raw)
    if not path.exists():
        return {}, f"Odometry state file not found: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"Odometry state file is unreadable: {exc}"
    return (payload if isinstance(payload, dict) else {}), None


async def _read_odometry_overlay() -> tuple[dict[str, Any], str | None]:
    return await asyncio.to_thread(_read_odometry_overlay_sync)


def _bool_from(payload: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _float_from(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _topic_diag(
    *,
    topic: str | None = None,
    status: str,
    detail: str | None = None,
) -> dict[str, str]:
    data = {"status": status}
    if topic:
        data["topic"] = topic
    if detail:
        data["detail"] = detail
    return data


async def _probe_bridge(bridge_url: str, *, enabled: bool) -> tuple[bool | None, str | None]:
    if not bridge_url:
        return False, "WAREHOUSE_ROS_BRIDGE_URL is not configured."
    if not enabled:
        return None, "Bridge URL configured; deep probe not requested."
    url = bridge_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        if response.status_code < 400:
            return True, f"Bridge health reachable at {url}"
        return False, f"Bridge health returned HTTP {response.status_code}"
    except Exception as exc:
        return False, f"Bridge health unreachable at {url}: {exc}"


async def build_preflight_snapshot(
    db: AsyncSession,
    *,
    user: Any,
    deep: bool,
    force: bool,
    mission_loaded: bool,
    start_bridge: bool = False,
) -> WarehousePreflightOut:
    bridge_url = str(getattr(settings, "WAREHOUSE_ROS_BRIDGE_URL", "") or "").strip()
    bridge_flow = str(getattr(settings, "WAREHOUSE_BRIDGE_FLOW", "") or "").strip().lower()
    ws = ros2_workspace()
    bridge_configured = (
        ws.exists() or bool(bridge_url) or bridge_flow not in {"", "disabled", "off", "none"}
    )
    auto_start_bridge = bridge_flow not in {"", "disabled", "off", "none"}
    should_start_bridge = bool(start_bridge and auto_start_bridge)
    ros_ok, ros_detail = await ensure_ros_bridge_running(start=should_start_bridge)
    http_ok: bool | None = None
    http_detail: str | None = None
    if not ws.exists():
        http_ok, http_detail = await _probe_bridge(bridge_url, enabled=bool(bridge_url and deep))
    bridge_ok = (
        True
        if ros_ok is True or http_ok is True
        else (False if ros_ok is False and http_ok is False else None)
    )
    bridge_detail = "; ".join(detail for detail in (ros_detail, http_detail) if detail) or None

    telemetry = telemetry_manager.runtime_snapshot()
    telemetry_running = bool(telemetry.get("running"))
    source_connected = bool(telemetry.get("source_connected"))
    last_update = float(telemetry.get("last_update") or 0.0)
    telemetry_age_ms = int(max(0.0, time.time() - last_update) * 1000) if last_update else None
    telemetry_fresh = telemetry_age_ms is not None and telemetry_age_ms <= 5_000

    overlay, overlay_error = await _read_odometry_overlay()
    topic_probe_error: str | None = None
    perception_status = await fetch_warehouse_perception_status(deep=True, force=force)
    topic_overlay = dict(perception_status.components or {})
    overlay = {**overlay, **topic_overlay}
    if topic_overlay.get("preflight_core_ready") is True:
        overlay_error = None
    probe_flags = (
        overlay.get("components") if isinstance(overlay.get("components"), dict) else overlay
    )
    local_position_ok = probe_flags.get("local_position_ok") is True
    slam_ready = probe_flags.get("slam_ready") is True
    slam_tracking_ok = probe_flags.get("slam_tracking_ok") is True
    tf_ok = probe_flags.get("tf_ok") is True
    nvblox_ok = _bool_from(overlay, "nvblox_ok", "nvblox_healthy", "nvblox_ready")
    sensors_flag = probe_flags.get("sensors_ok")
    sensors_ok = sensors_flag if isinstance(sensors_flag, bool) else None
    rgb_depth_imu_flag = probe_flags.get("rgb_depth_imu_ok")
    rgb_depth_imu_ok = rgb_depth_imu_flag if isinstance(rgb_depth_imu_flag, bool) else None
    lidar_flag = probe_flags.get("lidar_ok")
    lidar_ok = lidar_flag if isinstance(lidar_flag, bool) else None
    source_transport_flag = probe_flags.get("source_transport_ok")
    source_transport_ok = source_transport_flag if isinstance(source_transport_flag, bool) else None
    stable_ms = int(_float_from(overlay, "perception_stable_for_ms", "stable_for_ms") or 0)
    required_stable_ms = int(
        _float_from(overlay, "perception_required_stable_ms", "required_stable_ms") or 8_000
    )
    stability_ok = (
        stable_ms >= required_stable_ms
        and local_position_ok is True
        and (slam_tracking_ok is True or slam_ready is True)
    )

    map_count = len(
        await repo.list_warehouse_maps(
            db,
            owner_id=int(user.id),
            org_id=user.org_id,
            allow_org_access=can_access_org_scope(user),
            limit=1,
        )
    )
    rigs = await repo.list_sensor_rigs(
        db,
        owner_id=int(user.id),
        org_id=user.org_id,
        allow_org_access=can_access_org_scope(user),
        limit=50,
    )
    valid_rig_count = sum(
        1
        for rig in rigs
        if rig.calibration_status == "valid"
        and rig.intrinsics_url
        and rig.extrinsics_json
        and rig.calibration_hash
    )

    categories = {
        "bridge": _status(bridge_ok if bridge_configured else False),
        "vehicle_link": _status(source_connected),
        "telemetry_stream": _status(telemetry_running and telemetry_fresh),
        "source_transport": _status(source_transport_ok, required=False),
        "rgb_depth_imu": _status(rgb_depth_imu_ok, required=False),
        "lidar": _status(lidar_ok, required=False),
        "sensors": _status(sensors_ok if sensors_ok is not None else valid_rig_count > 0),
        "odometry": _status(local_position_ok),
        "localization": _status(slam_ready if slam_ready is not None else slam_tracking_ok),
        "tf": _status(tf_ok),
        "nvblox": _status(nvblox_ok, required=False),
        "stability": _status(stability_ok),
        "warehouse_map": _status(map_count > 0),
        "sensor_rig": _status(valid_rig_count > 0),
    }
    required_keys = [
        "bridge",
        "vehicle_link",
        "telemetry_stream",
        "sensors",
        "odometry",
        "localization",
        "tf",
        "stability",
        "warehouse_map",
        "sensor_rig",
    ]
    blockers: list[str] = []
    if not bridge_configured:
        blockers.append("Warehouse ROS bridge is disabled or not configured.")
    elif bridge_ok is not True:
        blockers.append(bridge_detail or "Warehouse ROS bridge is not ready.")
    if map_count == 0:
        blockers.append("Create or select a warehouse map.")
    if valid_rig_count == 0:
        blockers.append("Add a calibrated warehouse sensor rig.")
    if not source_connected:
        blockers.append("Drone link is not connected.")
    if not telemetry_running or not telemetry_fresh:
        blockers.append("Telemetry stream is not live.")
    blockers.extend(missing_critical_topic_blockers(overlay))
    if local_position_ok is not True and not any(
        "odometry topic" in blocker.lower() for blocker in blockers
    ):
        blockers.append("Local odometry is not available per warehouse_bridge.yaml.")
    if tf_ok is not True:
        blockers.append("TF tree is missing or stale.")
    if stability_ok is not True:
        blockers.append("Perception stability window has not passed.")
    if overlay_error and overlay_error != "WAREHOUSE_ODOMETRY_STATE_PATH is not configured.":
        blockers.append(overlay_error)
    if topic_probe_error:
        blockers.append(topic_probe_error)

    ros_report = await run_warehouse_ros_preflight_report(
        default_warehouse_scan_preflight_mission_data(),
        cruise_alt=2.0,
        force=force,
        source="ui_poll",
        perception_status=perception_status,
    )
    ros_can_start, blockers, ros_failed_checks = apply_ros_preflight_gate(
        categories,
        blockers,
        report=ros_report,
    )
    if categories["odometry"] != "OK":
        local_position_ok = False
    if categories["localization"] == "FAIL":
        slam_ready = False
        slam_tracking_ok = False
    if categories["bridge"] == "FAIL":
        bridge_ok = False
    if categories["tf"] == "FAIL":
        tf_ok = False

    ready_to_fly = (
        ros_can_start and not blockers and all(categories[key] == "OK" for key in required_keys)
    )
    checks = [{"id": key, "status": value} for key, value in categories.items()]
    topic_diag = {
        "bridge": _topic_diag(
            topic=bridge_url or None,
            status=categories["bridge"],
            detail=bridge_detail,
        ),
        "source_transport": _topic_diag(status=categories["source_transport"]),
        "rgb_depth_imu": _topic_diag(
            topic=str(overlay.get("rgb_topic") or ""),
            status=categories["rgb_depth_imu"],
        ),
        "lidar": _topic_diag(
            topic=str(overlay.get("lidar_topic") or ""),
            status=categories["lidar"],
        ),
        "odometry": _topic_diag(
            topic=str(overlay.get("odometry_topic") or ""),
            status=categories["odometry"],
        ),
        "tf": _topic_diag(status=categories["tf"], detail=None if tf_ok else "TF missing"),
        "nvblox": _topic_diag(
            topic=str(overlay.get("nvblox_topic") or "/nvblox_node/static_esdf_pointcloud"),
            status=categories["nvblox"],
            detail=(
                None
                if nvblox_ok is True
                else (
                    "Nvblox is optional for basic readiness, but required before "
                    "autonomous warehouse mapping flight."
                )
            ),
        ),
    }
    return WarehousePreflightOut(
        ready=ready_to_fly,
        blocking=not ready_to_fly,
        checks=checks,
        ready_to_fly=ready_to_fly,
        service_health=bridge_ok is True,
        ros_graph_ready=bridge_ok is True,
        mapping_ok=nvblox_ok,
        primary_blocker=blockers[0] if blockers else None,
        blockers=blockers,
        diagnostics_age_ms=telemetry_age_ms,
        mode="warehouse",
        localization_mode="local_odom",
        topic_health=topic_diag,
        tf_health={"ok": tf_ok, "detail": None if tf_ok else "TF missing"},
        stability_window_ms=stable_ms,
        required_stability_window_ms=required_stable_ms,
        bridge_ok=bridge_ok is True,
        source_transport_ok=source_transport_ok,
        sensors_ok=categories["sensors"] == "OK",
        odom_ok=local_position_ok is True,
        localization_ok=(slam_ready is True or slam_tracking_ok is True),
        tf_ok=tf_ok is True,
        nvblox_ok=nvblox_ok,
        stability_ok=stability_ok,
        vehicle_link_ok=source_connected,
        telemetry_stream_ok=telemetry_running and telemetry_fresh,
        battery_ok=True,
        perception_stable_for_ms=stable_ms,
        perception_required_stable_ms=required_stable_ms,
        ros_topic_count=int(_float_from(overlay, "ros_topic_count") or 0) or None,
        warehouse_bridge_state=(
            "ready" if bridge_ok is True else ("configured" if bridge_configured else "disabled")
        ),
        bridge_url=bridge_url or None,
        last_error=bridge_detail if bridge_ok is False else overlay_error,
        diagnostics={
            "bridge": {
                "api_reachable": bridge_ok,
                "status": categories["bridge"],
                "message": bridge_detail,
                "ros_domain_id": ros_command_env().get("ROS_DOMAIN_ID"),
                "health_probe_in_progress": False,
            },
            "topics": {
                "by_category": topic_diag,
                "deferred_missing": (
                    []
                    if nvblox_ok is not None
                    else [str(overlay.get("nvblox_topic") or "/nvblox_node/static_esdf_pointcloud")]
                ),
            },
            "bridge_topic_compatibility": {
                "configured_ros_topics": overlay.get("configured_ros_topics") or [],
                "missing_configured_ros_topics": overlay.get("missing_configured_ros_topics") or [],
                "configured_gz_topics": overlay.get("configured_gz_topics") or [],
                "missing_configured_gz_topics": overlay.get("missing_configured_gz_topics") or [],
                "gz_probe_error": overlay.get("gz_probe_error"),
                "probe_error": topic_probe_error,
            },
            "stability": {
                "stable_for_ms": stable_ms,
                "required_ms": required_stable_ms,
                "remaining_ms": max(0, required_stable_ms - stable_ms),
                "localization_mode": "local_odom",
                "tracking_ok": slam_tracking_ok,
                "odometry_topic": topic_diag["odometry"].get("topic"),
            },
            "freshness": {
                "diagnostics_age_ms": telemetry_age_ms,
                "diagnostics_stale": not telemetry_fresh,
                "stale_warn_threshold_ms": 5_000,
            },
            "setup": {
                "warehouse_maps": map_count,
                "sensor_rigs": len(rigs),
                "valid_sensor_rigs": valid_rig_count,
                "mission_loaded": mission_loaded,
            },
            "ros_preflight": {
                "overall_status": str(ros_report.overall_status),
                "can_start": ros_can_start,
                "failed_checks": ros_failed_checks,
                "base_checks": [
                    {"name": r.name, "status": str(r.status), "message": r.message}
                    for r in ros_report.base_checks
                ],
                "mission_checks": [
                    {"name": r.name, "status": str(r.status), "message": r.message}
                    for r in ros_report.mission_checks
                ],
            },
        },
        recommended_action=(
            None if ready_to_fly else "Resolve blockers, then rerun warehouse preflight."
        ),
        blocking_reasons=blockers,
        suggested_actions=blockers[:3],
        categories=categories,
        note="Warehouse preflight checks completed.",
    )


async def connect_drone_for_preflight() -> tuple[bool, str | None]:
    async with _preflight_drone_lock:
        try:
            orch = await build_orchestrator()
            if getattr(orch, "async_drone", None) is None:
                return False, "Drone runtime is not configured."
            if orch.async_drone.vehicle is None:
                await orch.async_drone.connect(home_fallback_allowed=True)
            if not telemetry_manager.runtime_snapshot()["running"]:
                await orch.start_live_telemetry()
            for _ in range(20):
                telemetry = telemetry_manager.runtime_snapshot()
                last_update = float(telemetry.get("last_update") or 0.0)
                fresh = last_update > 0 and (time.time() - last_update) <= 5.0
                if bool(telemetry.get("source_connected")) and fresh:
                    return True, None
                await asyncio.sleep(0.25)
            return False, "Drone connected, but telemetry is not fresh yet."
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Warehouse preflight drone connect failed: %s", exc)
            return False, f"Drone telemetry connect failed: {exc}"

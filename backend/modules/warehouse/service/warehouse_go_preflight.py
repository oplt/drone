from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field, replace
from typing import Any

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.service.bridge_supervisor import WarehouseBridgeSupervisorStatus
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import (
    SubsystemHealth,
    SubsystemStatus,
    check_bridge,
    check_failsafe,
    check_nvblox,
    check_planner,
    check_sensors,
    check_slam,
)
from backend.modules.warehouse.service.flight_readiness import (
    evaluate_subsystems_from_components,
    get_perception_stability_tracker,
)
from backend.modules.warehouse.service.readiness_result import (
    readiness_from_perception_status_strict,
)
from backend.modules.warehouse.service.warehouse_preflight import (
    build_warehouse_vehicle_state_from_perception,
    fetch_warehouse_perception_status,
)
from backend.modules.warehouse.service.warehouse_vehicle_checks import (
    check_telemetry_stream,
    check_vehicle_battery,
    check_vehicle_link,
    sim_ros_odometry_fallback_ok,
    vehicle_runtime_from_parts,
)
from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow
from backend.modules.warehouse.service.localization_mode import resolve_localization_mode


def _gazebo_sim_enabled(components: dict[str, Any] | None = None) -> bool:
    flow = resolve_warehouse_bridge_flow()
    if flow.name == "gazebo":
        return True
    if flow.name == "real_device":
        return False
    if os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    data = components or {}
    return bool(data.get("gazebo")) or str(data.get("topic_profile") or "").lower() == "gazebo"


def _topic_label(key: str, components: dict[str, Any]) -> str:
    topics = components.get("topics")
    if isinstance(topics, dict):
        topic = topics.get(key)
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    diag_raw = components.get("topic_diagnostics")
    if isinstance(diag_raw, dict):
        diag = diag_raw.get(key)
        if isinstance(diag, dict):
            matched = diag.get("matched") or diag.get("expected")
            if isinstance(matched, str) and matched.strip():
                return matched.strip()
    defaults = {
        "rgb_image": "/warehouse/contract/rgb/image",
        "depth": "/warehouse/contract/depth/image",
        "imu": "/warehouse/contract/imu",
        "visual_slam_odom": "/warehouse/contract/odometry",
    }
    return defaults.get(key, key)


def _topic_blocker(
    label: str,
    key: str,
    components: dict[str, Any],
    *,
    missing: bool,
) -> str:
    topic = _topic_label(key, components)
    if missing:
        return f"{label} topic missing ({topic})"
    return f"{label} topic stale or not publishing ({topic})"


def _gazebo_status(components: dict[str, Any]) -> tuple[bool | None, str | None]:
    if not _gazebo_sim_enabled(components):
        return None, None
    gazebo = components.get("gazebo")
    if not isinstance(gazebo, dict):
        return False, "Waiting for Gazebo sensor probe (start with: gz sim -r <world>.sdf)"
    if gazebo.get("sim_publishing") is True:
        return True, None
    missing = gazebo.get("missing_streams")
    if isinstance(missing, list) and missing:
        return False, f"Gazebo not publishing: {', '.join(str(item) for item in missing)}"
    return False, str(gazebo.get("start_hint") or "Press Play in Gazebo or use gz sim -r")


def _tf_ok(
    components: dict[str, Any],
    *,
    bridge_reachable: bool,
) -> tuple[bool, str | None]:
    if not bridge_reachable:
        return False, "TF not verified (warehouse bridge unreachable)"
    tf_tree = components.get("tf_tree")
    if tf_tree is False:
        return False, "TF tree invalid (odom→base_link→camera)"
    tf_raw = components.get("tf_chain")
    if isinstance(tf_raw, dict):
        if tf_raw.get("chain_ok") is False:
            if tf_raw.get("sim_clock_ready") is False:
                return (
                    False,
                    str(
                        tf_raw.get("detail")
                        or "Waiting for Gazebo /clock (press Play or gz sim -r <world>.sdf)"
                    ),
                )
            missing = tf_raw.get("missing_tf_edges") or []
            expected = tf_raw.get("required_tf_edges") or []
            if missing:
                if len(missing) == 1 and str(missing[0][0]) == "odom":
                    hint = (
                        "Press Play in Gazebo (or gz sim -r) so /clock and "
                        "warehouse_sim_tf_broadcaster can publish odom→base_link"
                    )
                    if tf_raw.get("validation_source", "").startswith("gazebo_odom"):
                        hint = (
                            "Odometry frames look correct but TF buffer is empty; "
                            "wait a few seconds or restart the bridge stack"
                        )
                    return False, f"TF missing: {missing}. {hint}"
                return (
                    False,
                    f"TF missing: {missing}"
                    + (f" (expected {expected})" if expected else ""),
                )
            return False, "Required TF chain missing (odom→base_link→camera)"
        if tf_raw.get("chain_ok") is True:
            return True, None
    if tf_tree is True:
        return True, None
    return False, "TF not verified (enable WAREHOUSE_TF_PROBE_ON_HEALTH=1 on bridge)"


def _nvblox_category(components: dict[str, Any]) -> tuple[bool | None, str]:
    """None = deferred until flight start (mapping stack not running)."""
    if components.get("nvblox_deferred") or not components.get("nvblox_checks_active"):
        return None, "Starts when warehouse scan begins (not required at idle)"
    if components.get("nvblox_healthy") or components.get("nvblox"):
        return True, "Nvblox outputs publishing"
    missing = components.get("missing_nvblox_topics") or []
    if missing:
        return False, f"Missing nvblox outputs: {', '.join(str(item) for item in missing)}"
    return False, "Nvblox outputs not ready"


@dataclass(frozen=True)
class WarehouseGoPreflight:
    ready_to_fly: bool
    service_health: bool
    ros_graph_ready: bool
    sensors_ok: bool
    localization_ok: bool
    mapping_ok: bool | None
    primary_blocker: str | None
    blockers: list[str]
    checks: list[dict[str, object]]
    diagnostics_age_ms: int | None
    mode: str
    localization_mode: str
    topic_health: dict[str, object]
    tf_health: dict[str, object]
    stability_window_ms: int
    required_stability_window_ms: int
    bridge_ok: bool
    gazebo_ok: bool | None
    odom_ok: bool
    tf_ok: bool
    nvblox_ok: bool | None
    stability_ok: bool
    vehicle_link_ok: bool
    telemetry_stream_ok: bool
    battery_ok: bool
    perception_stable_for_ms: int
    perception_required_stable_ms: int
    ros_topic_count: int | None
    warehouse_bridge_state: str = "stopped"
    bridge_url: str | None = None
    last_error: str | None = None
    restart_count: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    categories: dict[str, str] = field(default_factory=dict)
    note: str = (
        "HTTP 200 and /api/health only mean the app is alive. "
        "Use ready_to_fly for autonomous warehouse flight."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready_to_fly,
            "blocking": not self.ready_to_fly,
            "checks": self.checks or [
                {"id": key, "status": value} for key, value in self.categories.items()
            ],
            "ready_to_fly": self.ready_to_fly,
            "service_health": self.service_health,
            "ros_graph_ready": self.ros_graph_ready,
            "mapping_ok": self.mapping_ok,
            "primary_blocker": self.primary_blocker,
            "blockers": self.blockers,
            "diagnostics_age_ms": self.diagnostics_age_ms,
            "mode": self.mode,
            "localization_mode": self.localization_mode,
            "topic_health": self.topic_health,
            "tf_health": self.tf_health,
            "stability_window_ms": self.stability_window_ms,
            "required_stability_window_ms": self.required_stability_window_ms,
            "bridge_ok": self.bridge_ok,
            "gazebo_ok": self.gazebo_ok,
            "sensors_ok": self.sensors_ok,
            "odom_ok": self.odom_ok,
            "localization_ok": self.localization_ok,
            "tf_ok": self.tf_ok,
            "nvblox_ok": self.nvblox_ok,
            "stability_ok": self.stability_ok,
            "vehicle_link_ok": self.vehicle_link_ok,
            "telemetry_stream_ok": self.telemetry_stream_ok,
            "battery_ok": self.battery_ok,
            "perception_stable_for_ms": self.perception_stable_for_ms,
            "perception_required_stable_ms": self.perception_required_stable_ms,
            "ros_topic_count": self.ros_topic_count,
            "warehouse_bridge_state": self.warehouse_bridge_state,
            "bridge_url": self.bridge_url,
            "last_error": self.last_error,
            "restart_count": self.restart_count,
            "diagnostics": self.diagnostics,
            "recommended_action": self.suggested_actions[0] if self.suggested_actions else None,
            "blocking_reasons": self.blockers or self.blocking_reasons,
            "suggested_actions": self.suggested_actions,
            "categories": self.categories,
            "note": self.note,
        }


def _status_category(status: SubsystemStatus) -> str:
    return status.value


def _topic_path(key: str, components: dict[str, Any]) -> str:
    topics = components.get("topics")
    if isinstance(topics, dict):
        raw = topics.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    diag_raw = components.get("topic_diagnostics")
    if isinstance(diag_raw, dict):
        diag = diag_raw.get(key)
        if isinstance(diag, dict):
            raw = diag.get("matched") or diag.get("expected")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return _topic_label(key, components)


def _topic_hz_action(key: str, components: dict[str, Any]) -> str:
    return f"Verify: timeout 5 ros2 topic hz {_topic_path(key, components)}"


def _topic_status(key: str, components: dict[str, Any]) -> str:
    diag_raw = components.get("topic_diagnostics")
    diag = diag_raw.get(key) if isinstance(diag_raw, dict) else None
    if isinstance(diag, dict):
        state = str(diag.get("readiness_state") or "")
        if diag.get("healthy") is True:
            return "OK"
        if state in {"shallow_present", "no_messages", "probe_pending"}:
            return "WAITING"
        return "FAIL"
    if key == "raw_lidar" and components.get("raw_lidar_healthy") is True:
        return "OK"
    return "UNKNOWN"


def _topic_category(
    key: str,
    components: dict[str, Any],
    *,
    aliases: tuple[str, ...] = (),
    status_override: str | None = None,
) -> dict[str, object]:
    status = status_override or _topic_status(key, components)
    topic = _topic_path(key, components)
    alternatives = list(aliases)
    if key == "raw_lidar":
        alternatives = list(dict.fromkeys([*alternatives, "/scan", "/scan/points"]))
    return {
        "topic": topic,
        "status": status,
        "verify_cmd": f"timeout 5 ros2 topic hz {topic}",
        "alternatives": alternatives,
    }


def _aggregate_status(statuses: list[str]) -> str:
    if any(item == "FAIL" for item in statuses):
        return "FAIL"
    if any(item in {"WAITING", "UNKNOWN"} for item in statuses):
        return "WAITING"
    if any(item == "WARN" for item in statuses):
        return "WARN"
    return "OK"


def _wall_health_sample_age_ms(components: dict[str, Any]) -> int | None:
    import time

    raw = components.get("health_sample_timestamp")
    if not isinstance(raw, (int, float)):
        return None
    return max(0, int((time.time() - float(raw)) * 1000.0))


def _stability_reset_reason(
    *,
    bridge: SubsystemHealth,
    sensors: SubsystemHealth,
    slam: SubsystemHealth,
    nvblox: SubsystemHealth,
    components: dict[str, Any],
    config: WarehouseFlightConfig,
) -> str | None:
    if components.get("diagnostics_pending"):
        return "ROS diagnostics cache is warming"
    if components.get("probe_in_progress") and not components.get("cache_ready", True):
        return "bridge health probe is still running"
    if bridge.status != SubsystemStatus.OK:
        return f"bridge status is {bridge.status.value}: {bridge.message}"
    if sensors.status != SubsystemStatus.OK:
        return f"sensor status is {sensors.status.value}: {sensors.message}"
    if slam.status == SubsystemStatus.FAIL:
        return f"tracking status is not OK: {slam.message}"
    if (
        config.require_nvblox_for_autonomy
        and components.get("mapping_stack_running")
        and nvblox.status != SubsystemStatus.OK
    ):
        return f"nvblox status is {nvblox.status.value}: {nvblox.message}"
    return None


async def _fetch_vehicle_runtime() -> tuple[dict[str, Any], Telemetry | None, bool]:
    try:
        from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
        from backend.modules.missions.api.routes import get_orchestrator

        orch = await get_orchestrator()
        runtime_snapshot = telemetry_manager.runtime_snapshot()
        drone_connected = bool(
            runtime_snapshot.get("source_connected") or getattr(orch, "drone", None) is not None
        )
        autopilot: Telemetry | None = None
        drone = getattr(orch, "drone", None)
        if drone is not None:
            try:
                autopilot = await asyncio.to_thread(drone.get_telemetry)
            except Exception:
                autopilot = None
        return runtime_snapshot, autopilot, drone_connected
    except Exception:
        return {}, None, False


async def _ensure_bridge_for_preflight(
    *,
    autostart: bool,
) -> WarehouseBridgeSupervisorStatus | None:
    if not autostart:
        return None
    from backend.modules.warehouse.service.bridge_stack_lifecycle import (
        ensure_warehouse_bridge_stack_for_preflight,
    )

    return await ensure_warehouse_bridge_stack_for_preflight()


async def evaluate_warehouse_go_preflight(
    *,
    deep: bool = True,
    force: bool = False,
    mission_loaded: bool = False,
) -> WarehouseGoPreflight:
    autostart_bridge = bool(deep or force or mission_loaded)
    bridge_supervisor_status, (
        runtime_snapshot,
        autopilot_telemetry,
        drone_connected,
    ) = await asyncio.gather(
        _ensure_bridge_for_preflight(autostart=autostart_bridge),
        _fetch_vehicle_runtime(),
    )

    config = WarehouseFlightConfig.from_env()
    localization_mode = resolve_localization_mode()
    status = await fetch_warehouse_perception_status(deep=deep, force=force or deep)
    components = status.components if isinstance(status.components, dict) else {}
    components = {
        **components,
        "topic_profile": status.profile,
        "localization_mode": localization_mode.value,
    }
    if bridge_supervisor_status is not None:
        components = {
            **components,
            "bridge_stack_running": bridge_supervisor_status.running,
            "bridge_supervisor_state": bridge_supervisor_status.state,
        }
    if not config.gazebo_sim and str(status.profile or "").lower() == "gazebo":
        config = replace(config, gazebo_sim=True)
    strict = readiness_from_perception_status_strict(status)

    sim_ros_fallback = sim_ros_odometry_fallback_ok(components, config=config)
    vehicle_runtime = vehicle_runtime_from_parts(
        drone_connected=drone_connected,
        runtime_snapshot=runtime_snapshot,
        autopilot=autopilot_telemetry,
    )
    vehicle_link = check_vehicle_link(
        runtime=vehicle_runtime,
        config=config,
        sim_ros_fallback=sim_ros_fallback,
    )
    telemetry_stream = check_telemetry_stream(
        runtime=vehicle_runtime,
        config=config,
        sim_ros_fallback=sim_ros_fallback,
    )
    autopilot_for_battery = autopilot_telemetry
    if autopilot_for_battery is None and config.gazebo_sim:
        autopilot_for_battery = build_warehouse_vehicle_state_from_perception(status)
    battery = check_vehicle_battery(autopilot=autopilot_for_battery, config=config)

    vehicle_link_ok = vehicle_link.status == SubsystemStatus.OK
    telemetry_stream_ok = telemetry_stream.status == SubsystemStatus.OK
    battery_ok = battery.status in {SubsystemStatus.OK, SubsystemStatus.WARN}

    flight = evaluate_subsystems_from_components(
        status=status,
        components=components,
        telemetry=autopilot_telemetry,
        config=config,
        mission_loaded=mission_loaded,
        mission_valid=mission_loaded,
    )

    bridge = check_bridge(status, components)
    sensors = check_sensors(components, config)
    slam = check_slam(components, config, stable_for_ms=flight.slam_stable_for_ms)
    planner = check_planner(
        mission_loaded=mission_loaded,
        mission_valid=mission_loaded,
        speed_mps=None,
        altitude_m=None,
        config=config,
    )
    failsafe = check_failsafe()

    gazebo_ok, gazebo_reason = _gazebo_status(components)
    tf_ok, tf_reason = _tf_ok(components, bridge_reachable=status.reachable)
    nvblox_ok, _nvblox_message = _nvblox_category(components)

    perception_stable_ms = flight.perception_stable_for_ms
    stability_ok = perception_stable_ms >= config.perception_required_stable_ms
    stability_remaining_ms = max(0, config.perception_required_stable_ms - perception_stable_ms)

    stack_warming = bool(
        bridge_supervisor_status
        and bridge_supervisor_status.running
        and bridge_supervisor_status.state
        in {"starting", "process_running", "degraded"}
    )
    bridge_api_reachable = bool(
        (status.reachable and strict.bridge_alive) or stack_warming
    )
    bridge_ok = bridge_api_reachable and bridge.status != SubsystemStatus.FAIL
    bridge_flight_ready = bridge_api_reachable and bridge.status == SubsystemStatus.OK
    rgb_depth_imu_statuses = [
        _topic_status("rgb_image", components),
        _topic_status("depth", components),
        _topic_status("imu", components),
    ]
    rgb_depth_imu_category = _aggregate_status(rgb_depth_imu_statuses)
    lidar_category = (
        "OK"
        if strict.can_scan_lidar
        else "FAIL"
        if "raw_lidar" in strict.missing_required_topics or "raw_lidar" in strict.unhealthy_topics
        else _topic_status("raw_lidar", components)
    )
    sensors_ok = (
        sensors.status in {SubsystemStatus.OK, SubsystemStatus.WARN}
        and strict.can_perceive_rgb
        and strict.can_perceive_depth
        and strict.can_scan_lidar
    )
    odom_ok = slam.status != SubsystemStatus.FAIL and strict.can_localize
    localization_ok = slam.status == SubsystemStatus.OK

    blocking: list[str] = []
    suggested: list[str] = []

    if not bridge_api_reachable:
        if components.get("bridge_idle"):
            blocking.append("Warehouse ROS bridge is idle; run Warehouse Preflight to start it")
        else:
            blocking.append(bridge.message or "ROS bridge unreachable")
        suggested.append("Click Warehouse Preflight to start the ROS bridge stack")
    elif stack_warming and not status.reachable:
        blocking.append("Warehouse ROS bridge stack is starting")
        suggested.append("Wait for bridge HTTP on port 8088 and Gazebo contract topics")
    elif bridge.status in {SubsystemStatus.WAITING, SubsystemStatus.UNKNOWN}:
        blocking.append("Waiting for fresh bridge health sample")
        suggested.append("Wait for bridge health refresh to complete")
    elif bridge.status == SubsystemStatus.WARN:
        blocking.append(bridge.message or "Bridge health sample aging")
        suggested.append("Wait for background ROS health probe or run preflight with deep refresh")
    if gazebo_ok is False and gazebo_reason:
        blocking.append(gazebo_reason)
        suggested.append("Start the selected warehouse bridge flow and wait for adapter topics")
        suggested.append("Verify: timeout 5 ros2 topic hz /warehouse/contract/rgb/image")
    if not sensors_ok:
        if sensors.status == SubsystemStatus.FAIL or sensors.status in {
            SubsystemStatus.WAITING,
            SubsystemStatus.UNKNOWN,
        }:
            blocking.append(sensors.message)
        for key, label in (
            ("rgb_image", "RGB"),
            ("depth", "Depth"),
            ("imu", "IMU"),
            ("raw_lidar", "Raw lidar"),
        ):
            if key in strict.missing_required_topics:
                blocking.append(_topic_blocker(label, key, components, missing=True))
                suggested.append(_topic_hz_action(key, components))
            elif key in strict.unhealthy_topics:
                blocking.append(_topic_blocker(label, key, components, missing=False))
                suggested.append(_topic_hz_action(key, components))
    if not odom_ok:
        blocking.append(slam.message or "Local odometry unavailable")
        topic = components.get("odometry_topic") or _topic_label("visual_slam_odom", components)
        suggested.append(f"Verify: timeout 8 ros2 topic hz {topic}")
    if not tf_ok and tf_reason:
        blocking.append(tf_reason)
    if not stability_ok:
        remaining_s = stability_remaining_ms / 1000.0
        blocking.append(
            f"Core perception not stable long enough "
            f"({perception_stable_ms}ms / {config.perception_required_stable_ms}ms, "
            f"~{remaining_s:.1f}s remaining)"
        )
        suggested.append(
            "Wait until perception remains stable for "
            f"{config.perception_required_stable_ms // 1000} seconds"
        )
    if components.get("probe_in_progress") and not components.get("cache_ready"):
        blocking.append("ROS health probe in progress (ignoring transient topic drop)")
    if components.get("ros_topic_probe_error"):
        blocking.append(f"ROS topic probe: {components['ros_topic_probe_error']}")
    if not vehicle_link_ok:
        blocking.append(f"Drone telemetry missing: {vehicle_link.message}")
        suggested.append("Connect drone telemetry (Connect Drone) before warehouse flight")
    if not telemetry_stream_ok:
        blocking.append(f"Telemetry stream missing: {telemetry_stream.message}")
        suggested.append("Start MAVLink telemetry ingest and verify /ws/telemetry updates")
    if battery.status == SubsystemStatus.FAIL:
        blocking.append(f"Battery unavailable: {battery.message}")

    if strict.suggested_actions:
        suggested.extend(list(strict.suggested_actions))
    if not suggested:
        suggested.append("Run: scripts/check_warehouse_perception_topics.sh")

    # De-dupe while preserving order
    deduped_blocking: list[str] = []
    seen_blocking: set[str] = set()
    for item in blocking or flight.blocking_reasons:
        if item and item not in seen_blocking:
            seen_blocking.add(item)
            deduped_blocking.append(item)
    deduped_suggested: list[str] = []
    seen_suggested: set[str] = set()
    for item in suggested:
        if item and item not in seen_suggested:
            seen_suggested.add(item)
            deduped_suggested.append(item)

    ready_to_fly = (
        bridge_flight_ready
        and (gazebo_ok is not False)
        and sensors_ok
        and odom_ok
        and tf_ok
        and stability_ok
        and vehicle_link_ok
        and telemetry_stream_ok
        and battery_ok
        and flight.ready_to_takeoff
        and not components.get("odometry_state_unreadable")
    )

    ros_count_raw = components.get("ros_topic_count")
    ros_topic_count = int(ros_count_raw) if isinstance(ros_count_raw, int) else None
    bridge_category = (
        "FAIL"
        if not bridge_api_reachable or bridge.status == SubsystemStatus.FAIL
        else "OK"
        if bridge.status == SubsystemStatus.OK
        else "WAITING"
    )
    sensors_category = (
        "OK"
        if sensors_ok
        else "WAITING"
        if sensors.status in {SubsystemStatus.WAITING, SubsystemStatus.UNKNOWN}
        else "FAIL"
    )
    stability_reset_reason = _stability_reset_reason(
        bridge=bridge,
        sensors=sensors,
        slam=slam,
        nvblox=check_nvblox(components, config),
        components=components,
        config=config,
    )
    required_missing = list(strict.missing_required_topics)
    required_unhealthy = list(strict.unhealthy_topics)
    deferred_missing = (
        list(components.get("missing_nvblox_topics") or []) if nvblox_ok is None else []
    )
    diagnostics = {
        "bridge": {
            "process_state": (bridge_supervisor_status.state if bridge_supervisor_status else None),
            "api_reachable": bridge_api_reachable,
            "health_sample_age_ms": _wall_health_sample_age_ms(components),
            "health_probe_in_progress": bool(components.get("probe_in_progress")),
            "deep_ready": bool(status.ready),
            "status": bridge.status.value,
            "message": bridge.message,
        },
        "topics": {
            "required_missing": required_missing,
            "required_unhealthy": required_unhealthy,
            "deferred_missing": deferred_missing,
            "topic_diagnostics": components.get("topic_diagnostics") or {},
            "by_category": {
                "rgb": _topic_category("rgb_image", components),
                "depth": _topic_category("depth", components),
                "imu": _topic_category("imu", components),
                "lidar_scan": _topic_category(
                    "raw_lidar",
                    components,
                    aliases=("/scan", "/scan/points"),
                    status_override=lidar_category,
                ),
                "lidar_points": {
                    "topic": "/scan/points",
                    "status": "OK" if lidar_category == "OK" else lidar_category,
                    "verify_cmd": "timeout 5 ros2 topic hz /scan/points",
                },
            },
        },
        "stability": {
            "stable_for_ms": perception_stable_ms,
            "required_ms": config.perception_required_stable_ms,
            "remaining_ms": stability_remaining_ms,
            "last_reset_reason": stability_reset_reason,
            "last_successful_stable_ms": get_perception_stability_tracker().last_successful_stable_ms,
            "localization_mode": localization_mode.value,
            "tracking_ok": components.get("slam_tracking_ok"),
            "pose_quality_status": (
                "WARN"
                if sensors.details.get("local_pose_warning")
                else "OK"
                if sensors.status in {SubsystemStatus.OK, SubsystemStatus.WARN}
                else "FAIL"
            ),
            "pose_quality_metric": sensors.details.get("pose_age_ms"),
            "pose_quality_threshold": int(config.odometry_max_age_s * 1000),
            "odometry_topic": _topic_path("visual_slam_odom", components),
        },
    }

    categories = {
        "bridge": bridge_category,
        "gazebo": "N/A" if gazebo_ok is None else ("OK" if gazebo_ok else "FAIL"),
        "rgb_depth_imu": rgb_depth_imu_category,
        "lidar": lidar_category,
        "sensors": sensors_category,
        "odometry": "OK" if odom_ok else "FAIL",
        "localization": "OK" if localization_ok else "FAIL",
        "tf": "OK" if tf_ok else "FAIL",
        "nvblox": ("DEFERRED" if nvblox_ok is None else ("OK" if nvblox_ok else "FAIL")),
        "stability": "OK" if stability_ok else "WAITING",
        "vehicle_link": "OK" if vehicle_link_ok else "FAIL",
        "telemetry_stream": "OK" if telemetry_stream_ok else "FAIL",
        "battery": (
            "OK"
            if battery.status == SubsystemStatus.OK
            else ("FAIL" if battery.status == SubsystemStatus.FAIL else "WARN")
        ),
        "planner": planner.status.value,
        "failsafe": failsafe.status.value,
    }

    bridge_state = (
        bridge_supervisor_status.state
        if bridge_supervisor_status
        else ("ready" if status.reachable and status.ready else "degraded")
    )
    bridge_url = (
        bridge_supervisor_status.bridge_url if bridge_supervisor_status else status.bridge_url
    )
    bridge_last_error = (
        None
        if nvblox_ok is None
        and status.detail
        and all(str(item) in str(status.detail) for item in ("/nvblox_node/mesh", "mesh"))
        else deduped_blocking[0]
        if deduped_blocking
        else ("Waiting for perception stability window" if not stability_ok else None)
    )
    bridge_restart_count = bridge_supervisor_status.restart_count if bridge_supervisor_status else 0

    topic_health_payload = {
        key: diag if isinstance(diag, dict) else {}
        for key, diag in (components.get("topic_diagnostics") or {}).items()
    }
    tf_chain_raw = components.get("tf_chain")
    tf_health_payload = (
        tf_chain_raw
        if isinstance(tf_chain_raw, dict)
        else {"chain_ok": components.get("tf_tree"), "detail": tf_reason}
    )
    check_rows = [
        {"id": key, "label": key, "status": value}
        for key, value in categories.items()
    ]
    primary_blocker = deduped_blocking[0] if deduped_blocking else None

    if ready_to_fly:
        from backend.modules.warehouse.service.readiness_cache import record_sensor_readiness

        record_sensor_readiness(ready=True, payload=strict.to_dict())

    return WarehouseGoPreflight(
        ready_to_fly=ready_to_fly,
        service_health=bridge_api_reachable,
        ros_graph_ready=bool(strict.ros_graph_ready),
        sensors_ok=sensors_ok,
        localization_ok=localization_ok,
        mapping_ok=nvblox_ok,
        primary_blocker=primary_blocker,
        blockers=deduped_blocking,
        checks=check_rows,
        diagnostics_age_ms=_wall_health_sample_age_ms(components),
        mode="preflight",
        localization_mode=localization_mode.value,
        topic_health=topic_health_payload,
        tf_health=tf_health_payload,
        stability_window_ms=perception_stable_ms,
        required_stability_window_ms=config.perception_required_stable_ms,
        bridge_ok=bridge_ok,
        gazebo_ok=gazebo_ok,
        odom_ok=odom_ok,
        tf_ok=tf_ok,
        nvblox_ok=nvblox_ok,
        stability_ok=stability_ok,
        vehicle_link_ok=vehicle_link_ok,
        telemetry_stream_ok=telemetry_stream_ok,
        battery_ok=battery_ok,
        perception_stable_for_ms=perception_stable_ms,
        perception_required_stable_ms=config.perception_required_stable_ms,
        ros_topic_count=ros_topic_count,
        warehouse_bridge_state=bridge_state,
        bridge_url=bridge_url,
        last_error=bridge_last_error,
        restart_count=bridge_restart_count,
        diagnostics=diagnostics,
        blocking_reasons=deduped_blocking,
        suggested_actions=deduped_suggested,
        categories=categories,
    )

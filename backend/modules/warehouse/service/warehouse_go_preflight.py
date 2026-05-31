from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import (
    SubsystemStatus,
    check_bridge,
    check_failsafe,
    check_planner,
    check_sensors,
    check_slam,
)
from backend.modules.warehouse.service.flight_readiness import evaluate_subsystems_from_components
from backend.modules.warehouse.service.readiness_result import readiness_from_perception_status_strict
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


def _gazebo_sim_enabled() -> bool:
    return os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
        "rgb_image": "/warehouse/front/rgbd/image",
        "depth": "/warehouse/front/rgbd/depth_image",
        "imu": "/imu",
        "visual_slam_odom": os.getenv("WAREHOUSE_ODOMETRY_TOPIC", "/warehouse/drone/odometry"),
    }
    return defaults.get(key, key)


def _gazebo_status(components: dict[str, Any]) -> tuple[bool | None, str | None]:
    if not _gazebo_sim_enabled():
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


def _tf_ok(components: dict[str, Any]) -> tuple[bool, str | None]:
    tf_tree = components.get("tf_tree")
    if tf_tree is False:
        return False, "TF tree invalid (odom→base_link→camera)"
    tf_raw = components.get("tf_chain")
    if isinstance(tf_raw, dict) and tf_raw.get("chain_ok") is False:
        return False, "Required TF chain missing"
    return True, None


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
    bridge_ok: bool
    gazebo_ok: bool | None
    sensors_ok: bool
    odom_ok: bool
    localization_ok: bool
    tf_ok: bool
    nvblox_ok: bool | None
    stability_ok: bool
    vehicle_link_ok: bool
    telemetry_stream_ok: bool
    battery_ok: bool
    perception_stable_for_ms: int
    perception_required_stable_ms: int
    ros_topic_count: int | None
    blocking_reasons: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    categories: dict[str, str] = field(default_factory=dict)
    note: str = (
        "HTTP 200 and /api/health only mean the app is alive. "
        "Use ready_to_fly for autonomous warehouse flight."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready_to_fly": self.ready_to_fly,
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
            "blocking_reasons": self.blocking_reasons,
            "suggested_actions": self.suggested_actions,
            "categories": self.categories,
            "note": self.note,
        }


async def _fetch_vehicle_runtime() -> tuple[dict[str, Any], Telemetry | None, bool]:
    try:
        from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
        from backend.modules.missions.api.routes import get_orchestrator

        orch = await get_orchestrator()
        runtime_snapshot = telemetry_manager.runtime_snapshot()
        drone_connected = bool(
            runtime_snapshot.get("source_connected")
            or getattr(orch, "drone", None) is not None
        )
        autopilot = await asyncio.to_thread(orch.drone.get_telemetry)
        return runtime_snapshot, autopilot, drone_connected
    except Exception:
        return {}, None, False


async def evaluate_warehouse_go_preflight(
    *,
    deep: bool = True,
    force: bool = False,
    mission_loaded: bool = False,
) -> WarehouseGoPreflight:
    config = WarehouseFlightConfig.from_env()
    status = await fetch_warehouse_perception_status(deep=deep, force=force)
    components = status.components if isinstance(status.components, dict) else {}
    strict = readiness_from_perception_status_strict(status)

    runtime_snapshot, autopilot_telemetry, drone_connected = await _fetch_vehicle_runtime()
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
    tf_ok, tf_reason = _tf_ok(components)
    nvblox_ok, nvblox_message = _nvblox_category(components)

    perception_stable_ms = flight.perception_stable_for_ms
    stability_ok = perception_stable_ms >= config.perception_required_stable_ms

    bridge_ok = bridge.status == SubsystemStatus.OK and strict.bridge_alive
    sensors_ok = sensors.status == SubsystemStatus.OK and strict.can_perceive_rgb and strict.can_perceive_depth
    odom_ok = slam.status != SubsystemStatus.FAIL and strict.can_localize
    localization_ok = slam.status == SubsystemStatus.OK

    blocking: list[str] = []
    suggested: list[str] = []

    if not bridge_ok:
        blocking.append(bridge.message or "ROS bridge unreachable")
        suggested.append("Ensure warehouse_bridge is running on WAREHOUSE_ROS_BRIDGE_URL")
    if gazebo_ok is False and gazebo_reason:
        blocking.append(gazebo_reason)
        suggested.append("Start Gazebo with: gz sim -r <warehouse_world>.sdf")
        suggested.append("Verify: gz topic -e -t /warehouse/front/rgbd/image")
    if not sensors_ok:
        if sensors.status == SubsystemStatus.FAIL:
            blocking.append(sensors.message)
        for key, label in (
            ("rgb_image", "RGB"),
            ("depth", "Depth"),
            ("imu", "IMU"),
        ):
            if key in strict.missing_required_topics:
                blocking.append(f"{label} topic missing ({_topic_label(key, components)})")
            elif key in strict.unhealthy_topics:
                blocking.append(f"{label} topic stale or not publishing ({_topic_label(key, components)})")
    if not odom_ok:
        blocking.append(slam.message or "Local odometry unavailable")
        topic = components.get("odometry_topic") or _topic_label("visual_slam_odom", components)
        suggested.append(f"Verify: timeout 8 ros2 topic hz {topic}")
    if not tf_ok and tf_reason:
        blocking.append(tf_reason)
    if not stability_ok:
        remaining_s = max(
            0.0,
            (config.perception_required_stable_ms - perception_stable_ms) / 1000.0,
        )
        blocking.append(
            f"Core perception not stable long enough "
            f"({perception_stable_ms}ms / {config.perception_required_stable_ms}ms, "
            f"~{remaining_s:.1f}s remaining)"
        )
    if components.get("probe_in_progress") and not components.get("cache_ready"):
        blocking.append("ROS health probe in progress (ignoring transient topic drop)")
    if components.get("ros_topic_probe_error"):
        blocking.append(f"ROS topic probe: {components['ros_topic_probe_error']}")
    if not vehicle_link_ok:
        blocking.append(vehicle_link.message)
        suggested.append("Connect drone telemetry (Connect Drone) before warehouse flight")
    if not telemetry_stream_ok:
        blocking.append(telemetry_stream.message)
        suggested.append("Start MAVLink telemetry ingest and verify /ws/telemetry updates")
    if battery.status == SubsystemStatus.FAIL:
        blocking.append(battery.message)

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
        bridge_ok
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

    categories = {
        "bridge": "OK" if bridge_ok else "FAIL",
        "gazebo": "N/A" if gazebo_ok is None else ("OK" if gazebo_ok else "FAIL"),
        "sensors": "OK" if sensors_ok else "FAIL",
        "odometry": "OK" if odom_ok else "FAIL",
        "localization": "OK" if localization_ok else "FAIL",
        "tf": "OK" if tf_ok else "FAIL",
        "nvblox": (
            "DEFERRED"
            if nvblox_ok is None
            else ("OK" if nvblox_ok else "FAIL")
        ),
        "stability": "OK" if stability_ok else "WAITING",
        "vehicle_link": vehicle_link.status.value,
        "telemetry_stream": telemetry_stream.status.value,
        "battery": battery.status.value,
        "planner": planner.status.value,
        "failsafe": failsafe.status.value,
    }

    return WarehouseGoPreflight(
        ready_to_fly=ready_to_fly,
        bridge_ok=bridge_ok,
        gazebo_ok=gazebo_ok,
        sensors_ok=sensors_ok,
        odom_ok=odom_ok,
        localization_ok=localization_ok,
        tf_ok=tf_ok,
        nvblox_ok=nvblox_ok,
        stability_ok=stability_ok,
        vehicle_link_ok=vehicle_link_ok,
        telemetry_stream_ok=telemetry_stream_ok,
        battery_ok=battery_ok,
        perception_stable_for_ms=perception_stable_ms,
        perception_required_stable_ms=config.perception_required_stable_ms,
        ros_topic_count=ros_topic_count,
        blocking_reasons=deduped_blocking,
        suggested_actions=deduped_suggested,
        categories=categories,
    )

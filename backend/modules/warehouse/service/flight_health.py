from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.readiness_result import (
    _topic_diag,
    topic_is_strictly_live,
)
from backend.modules.warehouse.service.runtime_safety import (
    evaluate_local_odometry,
    odometry_display_name,
    odometry_state_is_fresh,
    odometry_topic_path,
)


class SubsystemStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    WAITING = "WAITING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SubsystemHealth:
    status: SubsystemStatus
    message: str
    last_seen_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }
        if self.last_seen_ms is not None:
            payload["last_seen_ms"] = self.last_seen_ms
        return payload


def _age_ms_from_diag(diag: dict[str, Any] | None) -> int | None:
    if diag is None:
        return None
    age_s = diag.get("last_message_age_s")
    if isinstance(age_s, (int, float)):
        return max(0, int(float(age_s) * 1000.0))
    return None


def _status_from_age(
    age_ms: int | None,
    *,
    max_age_ms: int,
    missing_message: str,
) -> SubsystemHealth:
    if age_ms is None:
        return SubsystemHealth(SubsystemStatus.FAIL, missing_message)
    if age_ms <= max_age_ms:
        return SubsystemHealth(
            SubsystemStatus.OK,
            f"Fresh ({age_ms}ms)",
            last_seen_ms=age_ms,
        )
    warn_threshold = int(max_age_ms * 1.5)
    if age_ms <= warn_threshold:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            f"Near threshold ({age_ms}ms / {max_age_ms}ms)",
            last_seen_ms=age_ms,
            details={"max_age_ms": max_age_ms},
        )
    return SubsystemHealth(
        SubsystemStatus.FAIL,
        f"Stale ({age_ms}ms / {max_age_ms}ms)",
        last_seen_ms=age_ms,
        details={"max_age_ms": max_age_ms},
    )


def check_bridge(
    status: WarehousePerceptionStatus,
    components: dict[str, Any],
) -> SubsystemHealth:
    from backend.modules.warehouse.service.perception_stability import diagnostics_probe_pending

    if diagnostics_probe_pending(components):
        return SubsystemHealth(
            SubsystemStatus.WAITING,
            "ROS health probe in progress",
            details={"probe_in_progress": True},
        )
    if not status.configured:
        return SubsystemHealth(
            SubsystemStatus.WAITING,
            "Warehouse ROS bridge not configured",
        )
    if not status.reachable:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Warehouse ROS bridge unreachable",
        )
    heartbeat = components.get("ros_bridge_heartbeat")
    if heartbeat is False:
        return SubsystemHealth(SubsystemStatus.FAIL, "ROS bridge heartbeat lost")
    sample_ts = components.get("health_sample_timestamp")
    last_seen_ms = None
    if isinstance(sample_ts, (int, float)):
        last_seen_ms = max(0, int((time.time() - float(sample_ts)) * 1000.0))
    max_sample_age_ms = int(
        components.get("health_sample_max_age_ms")
        or components.get("health_cache_ttl_ms")
        or 30_000
    )
    if last_seen_ms is not None and last_seen_ms > max_sample_age_ms:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "Bridge health sample aging",
            last_seen_ms=last_seen_ms,
            details={"max_age_ms": max_sample_age_ms},
        )
    return SubsystemHealth(
        SubsystemStatus.OK,
        "MAVLink/ROS bridge heartbeat fresh",
        last_seen_ms=last_seen_ms or 0,
        details={"bridge_url": status.bridge_url},
    )


def check_autopilot(
    *,
    telemetry: Telemetry | None,
    components: dict[str, Any],
    config: WarehouseFlightConfig,
) -> SubsystemHealth:
    if telemetry is None:
        if config.gazebo_sim:
            odom = components.get("local_odometry_state")
            odom_dict = odom if isinstance(odom, dict) else {}
            if odometry_state_is_fresh(
                odom_dict,
                max_age_s=config.pose_max_age_ms / 1000.0,
            ):
                return SubsystemHealth(
                    SubsystemStatus.OK,
                    "Gazebo sim: ROS odometry substituting autopilot state",
                    details={"sim_mode": True},
                )
            return SubsystemHealth(
                SubsystemStatus.WARN,
                "Gazebo sim: MAVLink unavailable; waiting for ROS odometry",
                details={"sim_mode": True},
            )
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Autopilot telemetry unavailable",
        )

    heartbeat_age_s = telemetry.heartbeat_age_s
    if heartbeat_age_s is None:
        return SubsystemHealth(SubsystemStatus.FAIL, "No autopilot heartbeat")
    heartbeat_ms = int(float(heartbeat_age_s) * 1000.0)
    if heartbeat_ms > config.max_command_latency_ms * 2:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Autopilot heartbeat stale",
            last_seen_ms=heartbeat_ms,
        )
    if heartbeat_ms > config.max_command_latency_ms:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "Autopilot heartbeat latency high",
            last_seen_ms=heartbeat_ms,
            details={"max_latency_ms": config.max_command_latency_ms},
        )

    if telemetry.is_armable is False:
        return SubsystemHealth(SubsystemStatus.FAIL, "Pre-arm checks failing")
    if not telemetry.mode:
        return SubsystemHealth(SubsystemStatus.FAIL, "Flight mode not readable")

    battery = telemetry.battery_remaining
    if battery is not None and battery < config.min_battery_percent:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            f"Battery below minimum ({battery:.0f}% < {config.min_battery_percent:.0f}%)",
            details={"battery_percent": battery},
        )
    if battery is not None and battery < config.min_battery_percent + 10:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            f"Battery low ({battery:.0f}%)",
            details={"battery_percent": battery},
        )

    return SubsystemHealth(
        SubsystemStatus.OK,
        "Pre-arm checks passed",
        last_seen_ms=heartbeat_ms,
        details={
            "mode": telemetry.mode,
            "battery_percent": battery,
            "armable": telemetry.is_armable,
        },
    )


GAZEBO_SENSOR_START_HINT = (
    "Gazebo sensors not publishing. Start with gz sim -r <world>.sdf or press Play, "
    "then verify: gz topic -e -t /warehouse/front/rgbd/image"
)


def _diag_idle_reason(diag: dict[str, Any] | None) -> str | None:
    if diag is None:
        return None
    state = diag.get("readiness_state")
    if state in {"shallow_present", "no_messages"}:
        return str(state)
    if diag.get("healthy") is False and not diag.get("publishing"):
        return "not_publishing"
    return None


def check_gazebo_sensors(
    components: dict[str, Any],
    config: WarehouseFlightConfig,
) -> SubsystemHealth | None:
    if not config.gazebo_sim and not config.require_gazebo_publishing:
        return None
    gazebo = components.get("gazebo")
    if not isinstance(gazebo, dict):
        if config.gazebo_sim:
            return SubsystemHealth(
                SubsystemStatus.WAITING,
                "Waiting for Gazebo sensor probe",
                details={"hint": GAZEBO_SENSOR_START_HINT},
            )
        return None
    if gazebo.get("sim_publishing") is True:
        return SubsystemHealth(
            SubsystemStatus.OK,
            "Gazebo RGB, depth, and odometry publishing",
            details=gazebo,
        )
    missing: list[str] = []
    if not gazebo.get("rgb_publishing"):
        missing.append("rgb")
    if not gazebo.get("depth_publishing"):
        missing.append("depth")
    if not gazebo.get("odom_publishing"):
        missing.append("odometry")
    hint = str(gazebo.get("start_hint") or GAZEBO_SENSOR_START_HINT)
    return SubsystemHealth(
        SubsystemStatus.FAIL,
        f"Gazebo sensors idle ({', '.join(missing) or 'unknown'}); {hint}",
        details={**gazebo, "missing_streams": missing},
    )


def check_sensors(
    components: dict[str, Any],
    config: WarehouseFlightConfig,
) -> SubsystemHealth:
    from backend.modules.warehouse.service.perception_stability import diagnostics_probe_pending

    if diagnostics_probe_pending(components):
        return SubsystemHealth(
            SubsystemStatus.WAITING,
            "Waiting for stable ROS topic diagnostics",
            details={"probe_in_progress": True},
        )

    odom_display = odometry_display_name(components, gazebo_sim=config.gazebo_sim)
    if components.get("odometry_state_unreadable"):
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            f"Local odometry state unreadable ({odom_display})",
            details={
                "odometry_topic": odometry_display_name(components, gazebo_sim=config.gazebo_sim),
                "hint": "Check odometry export node and: ros2 topic echo --once "
                f"{odometry_topic_path(components)}",
            },
        )

    gazebo_health = check_gazebo_sensors(components, config)
    if gazebo_health is not None and gazebo_health.status == SubsystemStatus.FAIL:
        return gazebo_health

    imu_diag = _topic_diag(components, "imu")
    depth_diag = _topic_diag(components, "depth")
    rgb_diag = _topic_diag(components, "rgb_image")
    lidar_diag = _topic_diag(components, "raw_lidar")
    vslam_diag = _topic_diag(components, "visual_slam_odom")

    require_raw_lidar = bool(
        components.get("require_raw_lidar")
        or (
            not config.gazebo_sim and str(components.get("topic_profile") or "").lower() != "gazebo"
        )
    )
    checks: list[tuple[str, dict[str, Any] | None, int, bool]] = [
        ("imu", imu_diag, config.imu_max_age_ms, True),
        ("depth", depth_diag, config.depth_max_age_ms, True),
        ("rgb", rgb_diag, config.rgb_max_age_ms, True),
        ("lidar", lidar_diag, config.depth_max_age_ms, require_raw_lidar),
        ("visual_slam_odom", vslam_diag, config.pose_max_age_ms, True),
    ]

    failures: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    for name, diag, max_ms, required in checks:
        label = odom_display if name == "visual_slam_odom" else name
        if diag is None:
            if required:
                failures.append(f"{label} missing")
            continue
        age_ms = _age_ms_from_diag(diag)
        live = topic_is_strictly_live(diag)
        details[f"{name}_age_ms"] = age_ms
        details[f"{name}_live"] = live
        if not live:
            idle = _diag_idle_reason(diag)
            if required:
                if idle in {"shallow_present", "no_messages", "not_publishing"}:
                    failures.append(
                        f"{label} listed but not publishing ({idle}); {GAZEBO_SENSOR_START_HINT}"
                        if config.gazebo_sim and name in {"rgb", "depth", "visual_slam_odom"}
                        else f"{label} not publishing"
                    )
                else:
                    failures.append(f"{label} not publishing")
            elif diag.get("listed"):
                warnings.append(f"{label} degraded")
            continue
        if age_ms is not None and age_ms > max_ms:
            if required:
                failures.append(f"{label} stale ({age_ms}ms)")
            else:
                warnings.append(f"{label} near threshold")

    odom_health = evaluate_local_odometry(
        components,
        max_age_s=config.odometry_max_age_s,
        gazebo_sim=config.gazebo_sim,
        strict_topic=True,
    )
    details["odometry_display_name"] = odom_health.display_name
    details["pose_age_ms"] = (
        int(odom_health.age_s * 1000.0) if odom_health.age_s is not None else None
    )
    if not odom_health.fresh:
        failures.append(
            f"local pose stale or missing ({odom_health.display_name}, "
            f"max {int(config.odometry_max_age_s * 1000)}ms)"
        )
    elif odom_health.age_s is not None and odom_health.age_s > (config.odometry_max_age_s * 0.8):
        details["local_pose_warning"] = f"local pose near threshold ({odom_health.display_name})"

    if failures:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "; ".join(failures),
            details=details,
        )
    if warnings:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "; ".join(warnings),
            details=details,
        )
    if gazebo_health is not None and gazebo_health.status == SubsystemStatus.WAITING:
        return gazebo_health
    return SubsystemHealth(SubsystemStatus.OK, "Sensor streams fresh", details=details)


def check_slam(
    components: dict[str, Any],
    config: WarehouseFlightConfig,
    *,
    stable_for_ms: int = 0,
) -> SubsystemHealth:
    odom_display = odometry_display_name(components, gazebo_sim=config.gazebo_sim)
    if components.get("odometry_state_unreadable"):
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            f"Localization odometry unreadable ({odom_display})",
            details={"odometry_display_name": odom_display},
        )

    odom_state = components.get("local_odometry_state")
    odom_dict = odom_state if isinstance(odom_state, dict) else {}
    tracking_ok = components.get("slam_tracking_ok")
    if tracking_ok is None:
        tracking_ok = odom_dict.get("slam_tracking_ok")
    if tracking_ok is False:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "SLAM tracking lost",
            details={
                "stable_for_ms": stable_for_ms,
                "required_stable_ms": config.slam_required_stable_ms,
                "odometry_display_name": odom_display,
            },
        )

    odom_health = evaluate_local_odometry(
        components,
        max_age_s=config.odometry_max_age_s,
        gazebo_sim=config.gazebo_sim,
        strict_topic=True,
    )
    if not odom_health.fresh:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            f"Localization odometry unavailable ({odom_health.display_name})",
            details={
                "odometry_age_s": odom_health.age_s,
                "max_age_s": config.odometry_max_age_s,
            },
        )

    confidence = odom_dict.get("localization_confidence")
    if isinstance(confidence, (int, float)) and float(confidence) < 0.4:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "SLAM localization confidence low",
            details={"localization_confidence": confidence},
        )

    return SubsystemHealth(
        SubsystemStatus.OK,
        f"Localization tracking via {odom_display}",
        details={
            "localization_confidence": confidence,
            "odometry_display_name": odom_display,
            "stable_for_ms": stable_for_ms,
            "required_stable_ms": config.slam_required_stable_ms,
        },
    )


def check_nvblox(
    components: dict[str, Any],
    config: WarehouseFlightConfig,
    *,
    mapping_stack_running: bool = False,
) -> SubsystemHealth:
    checks_active = bool(mapping_stack_running or components.get("nvblox_checks_active"))
    if components.get("nvblox_deferred") and not checks_active:
        return SubsystemHealth(
            SubsystemStatus.WAITING,
            "Nvblox verified when warehouse scan starts (mapping stack not running)",
            details={"deferred": True},
        )
    if not checks_active:
        return SubsystemHealth(
            SubsystemStatus.WAITING,
            "Waiting for nvblox mapping stack to start",
            details={"mapping_stack_running": mapping_stack_running},
        )

    nvblox_ready = bool(components.get("nvblox_healthy", components.get("nvblox")))
    if components.get("nvblox_warming_up"):
        return SubsystemHealth(
            SubsystemStatus.WAITING,
            "Nvblox warming up",
        )
    if not nvblox_ready:
        missing = components.get("missing_nvblox_topics") or []
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Nvblox not active or outputs missing",
            details={"missing_nvblox_topics": list(missing) if missing else []},
        )

    esdf_diag = _topic_diag(components, "esdf") or _topic_diag(components, "occupancy")
    costmap_age_ms = _age_ms_from_diag(esdf_diag if isinstance(esdf_diag, dict) else None)
    if costmap_age_ms is None:
        nvblox_fps = components.get("nvblox_fps")
        if isinstance(nvblox_fps, (int, float)) and float(nvblox_fps) > 0:
            costmap_age_ms = int(1000.0 / float(nvblox_fps))
        else:
            costmap_age_ms = None

    details: dict[str, Any] = {"costmap_age_ms": costmap_age_ms}
    if costmap_age_ms is None:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "Costmap freshness unknown",
            details=details,
        )
    if costmap_age_ms > config.costmap_max_age_ms:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "Costmap not fresh",
            details={**details, "max_age_ms": config.costmap_max_age_ms},
        )
    if costmap_age_ms > int(config.costmap_max_age_ms * 0.8):
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "Costmap age near threshold",
            details={**details, "max_age_ms": config.costmap_max_age_ms},
        )

    obstacle_m = components.get("obstacle_distance_m")
    if isinstance(obstacle_m, (int, float)):
        details["obstacle_distance_m"] = float(obstacle_m)
        if float(obstacle_m) < config.takeoff_clear_radius_m:
            return SubsystemHealth(
                SubsystemStatus.FAIL,
                "Takeoff zone not clear",
                details=details,
            )

    return SubsystemHealth(
        SubsystemStatus.OK,
        "Nvblox active; costmap fresh",
        last_seen_ms=costmap_age_ms,
        details=details,
    )


def check_planner(
    *,
    mission_loaded: bool,
    mission_valid: bool,
    speed_mps: float | None,
    altitude_m: float | None,
    config: WarehouseFlightConfig,
) -> SubsystemHealth:
    if not mission_loaded:
        return SubsystemHealth(SubsystemStatus.WAITING, "Mission not loaded")
    if not mission_valid:
        return SubsystemHealth(SubsystemStatus.FAIL, "Mission path or waypoints invalid")
    if speed_mps is not None and speed_mps > config.max_indoor_speed_mps:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            f"Speed above indoor limit ({speed_mps:.2f} m/s)",
            details={"max_speed_mps": config.max_indoor_speed_mps},
        )
    if altitude_m is not None and altitude_m > config.max_indoor_altitude_m:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            f"Altitude above indoor limit ({altitude_m:.2f} m)",
            details={"max_altitude_m": config.max_indoor_altitude_m},
        )
    return SubsystemHealth(
        SubsystemStatus.OK,
        "Mission loaded; planner constraints configured",
        details={
            "max_speed_mps": config.max_indoor_speed_mps,
            "max_altitude_m": config.max_indoor_altitude_m,
        },
    )


def check_failsafe(
    *,
    hover_fallback: bool = True,
    land_fallback: bool = True,
    manual_override: bool = True,
) -> SubsystemHealth:
    if not hover_fallback and not land_fallback:
        return SubsystemHealth(
            SubsystemStatus.FAIL,
            "No emergency hover/land fallback configured",
        )
    if not manual_override:
        return SubsystemHealth(
            SubsystemStatus.WARN,
            "Manual override availability not confirmed",
        )
    return SubsystemHealth(
        SubsystemStatus.OK,
        "Hover and land fallback configured",
        details={"hover": hover_fallback, "land": land_fallback},
    )

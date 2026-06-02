from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.runtime_safety import (
    default_odometry_max_age_s,
    evaluate_local_odometry,
)

FAILURE_USER_MESSAGES: dict[str, str] = {
    "odometry_topic_unavailable": (
        "Warehouse scan cannot start because local odometry is unavailable. "
        "Start the visual SLAM / odometry bridge and verify the odometry topic is publishing."
    ),
    "odometry_stale": (
        "Warehouse scan cannot continue because local odometry is stale. "
        "Verify the odometry topic is publishing: ros2 topic hz /warehouse/drone/odometry"
    ),
    "odometry_state_unreadable": (
        "Warehouse local odometry state is unreadable. "
        "Check the odometry export node and ros2 topic echo /warehouse/drone/odometry --once"
    ),
    "depth_topic_unavailable": (
        "Depth camera topic is missing or not publishing. Check the RGB-D camera bridge."
    ),
    "rgb_topic_unavailable": (
        "RGB camera topic is missing or not publishing. Check the camera bridge."
    ),
    "raw_lidar_unavailable": (
        "Lidar / pointcloud topic is missing. Check the Gazebo sensor plugin or ROS remapping."
    ),
    "nvblox_unavailable": (
        "3D mapping stack is degraded. nvblox output topics are missing or not publishing."
    ),
    "bridge_unreachable": (
        "Warehouse ROS bridge is unreachable. Ensure warehouse_bridge is running on port 8088."
    ),
    "ros_graph_unavailable": (
        "ROS graph is empty. Check ROS_DOMAIN_ID and that Gazebo sensor bridge is running."
    ),
    "warehouse_sensors_not_ready": (
        "Required warehouse sensor topics are not ready. Press Play in Gazebo and wait for sensors."
    ),
    "gazebo_sensors_idle": (
        "Gazebo sensors are listed but not publishing. Start with gz sim -r <world>.sdf or press Play, "
        "then verify RGB, depth, and odometry with gz topic -e."
    ),
}


def user_message_for_failure(
    failure_code: str,
    *,
    missing_topics: tuple[str, ...] = (),
    topic: str | None = None,
) -> str:
    base = FAILURE_USER_MESSAGES.get(
        failure_code,
        f"Warehouse scan cannot start ({failure_code}).",
    )
    parts = [base]
    if topic:
        parts.append(f"Expected topic: {topic}.")
    if missing_topics:
        parts.append(f"Missing or unhealthy: {', '.join(missing_topics)}.")
    return " ".join(parts)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _gazebo_sim_enabled(components: dict[str, object] | None = None) -> bool:
    if os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    data = components or {}
    return str(data.get("topic_profile") or data.get("profile") or "").lower() == "gazebo"


def _topic_diag(components: dict[str, object], key: str) -> dict[str, Any] | None:
    raw = components.get("topic_diagnostics")
    if not isinstance(raw, dict):
        return None
    diag = raw.get(key)
    return diag if isinstance(diag, dict) else None


def _component_missing_required_topics(components: dict[str, object]) -> set[str] | None:
    raw = components.get("missing_required_topics")
    if not isinstance(raw, list):
        return None
    return {str(item) for item in raw if item}


def topic_is_strictly_live(
    diag: dict[str, Any] | None,
    *,
    require_publisher: bool = True,
) -> bool:
    """Topic is live only when deep diagnostics mark it healthy with publishers/messages."""
    if diag is None:
        return False
    if not diag.get("healthy"):
        return False
    state = diag.get("readiness_state")
    if state in {"shallow_present", "topic_missing", "no_messages", "unhealthy", "probe_error"}:
        return False
    if require_publisher:
        publishers = int(diag.get("publisher_count") or 0)
        publishing = bool(diag.get("publishing"))
        if publishers <= 0 and not publishing:
            return False
    return True


def evaluate_warehouse_capabilities(
    status: WarehousePerceptionStatus,
    *,
    require_lidar: bool | None = None,
    require_nvblox_for_map: bool = False,
) -> dict[str, bool]:
    components = status.components if isinstance(status.components, dict) else {}
    if require_lidar is None:
        require_lidar = not _gazebo_sim_enabled(status.components) or os.getenv(
            "WAREHOUSE_TAKEOFF_REQUIRE_RAW_LIDAR", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}

    odom_max_age_s = _float_env("WAREHOUSE_TAKEOFF_ODOMETRY_MAX_AGE_S", default_odometry_max_age_s())
    odom_state_raw = components.get("local_odometry_state")
    odom_state = odom_state_raw if isinstance(odom_state_raw, dict) else {}
    odom_health = evaluate_local_odometry(
        components if isinstance(components, dict) else {},
        max_age_s=odom_max_age_s,
        strict_topic=True,
    )

    vslam_diag = _topic_diag(components, "visual_slam_odom")
    local_odom_diag = _topic_diag(components, "local_odometry")
    depth_diag = _topic_diag(components, "depth")
    rgb_diag = _topic_diag(components, "rgb_image")
    lidar_diag = _topic_diag(components, "raw_lidar")
    imu_diag = _topic_diag(components, "imu")

    can_localize = odom_health.fresh
    can_perceive_depth = topic_is_strictly_live(depth_diag)
    can_perceive_rgb = topic_is_strictly_live(rgb_diag)
    bridge_capabilities = components.get("capabilities")
    bridge_can_scan_lidar = (
        bool(bridge_capabilities.get("can_scan_lidar"))
        if isinstance(bridge_capabilities, dict)
        else False
    )
    can_scan_lidar = (
        topic_is_strictly_live(lidar_diag)
        or bridge_can_scan_lidar
        or bool(components.get("raw_lidar_healthy"))
        or not require_lidar
    )
    can_perceive_imu = topic_is_strictly_live(imu_diag)

    gazebo_ok = True
    if _gazebo_sim_enabled(components):
        gazebo_raw = components.get("gazebo")
        if isinstance(gazebo_raw, dict):
            gazebo_ok = gazebo_raw.get("sim_publishing") is True
        else:
            gazebo_ok = False

    nvblox_ready = bool(components.get("nvblox_healthy", components.get("nvblox")))
    capabilities_raw = components.get("capabilities")
    if isinstance(capabilities_raw, dict):
        can_map_3d = bool(capabilities_raw.get("can_map_3d", nvblox_ready))
    else:
        can_map_3d = nvblox_ready

    bridge_alive = bool(status.reachable)
    ros_graph_ready = bool(components.get("ros_graph"))

    can_fly = bool(
        bridge_alive
        and ros_graph_ready
        and gazebo_ok
        and can_localize
        and can_perceive_depth
        and can_perceive_rgb
        and can_scan_lidar
        and can_perceive_imu
    )
    can_build_map = bool(can_map_3d) if require_nvblox_for_map else can_fly

    return {
        "bridge_alive": bridge_alive,
        "ros_graph_ready": ros_graph_ready,
        "can_localize": can_localize,
        "can_perceive_depth": can_perceive_depth,
        "can_perceive_rgb": can_perceive_rgb,
        "can_scan_lidar": can_scan_lidar,
        "can_perceive_imu": can_perceive_imu,
        "can_map_3d": can_map_3d,
        "can_avoid_obstacles": can_map_3d,
        "can_fly_warehouse_scan": can_fly,
        "can_build_warehouse_map": can_build_map,
    }


@dataclass(frozen=True)
class WarehouseReadinessResult:
    bridge_alive: bool
    ros_graph_ready: bool
    can_localize: bool
    can_perceive_depth: bool
    can_perceive_rgb: bool
    can_scan_lidar: bool
    can_build_map: bool
    can_avoid_obstacles: bool
    can_fly_warehouse_scan: bool
    missing_required_topics: tuple[str, ...] = ()
    unhealthy_topics: tuple[str, ...] = ()
    missing_nvblox_topics: tuple[str, ...] = ()
    failure_code: str | None = None
    user_message: str | None = None
    developer_message: str | None = None
    suggested_actions: tuple[str, ...] = field(default_factory=tuple)
    topic_diagnostics: dict[str, object] = field(default_factory=dict)
    health_sample_timestamp: float | None = None
    from_cache: bool = False
    probe_mode: str | None = None

    @property
    def ready(self) -> bool:
        return self.can_fly_warehouse_scan

    def to_dict(self) -> dict[str, object]:
        return {
            "bridge_alive": self.bridge_alive,
            "ros_graph_ready": self.ros_graph_ready,
            "can_localize": self.can_localize,
            "can_perceive_depth": self.can_perceive_depth,
            "can_perceive_rgb": self.can_perceive_rgb,
            "can_scan_lidar": self.can_scan_lidar,
            "can_build_map": self.can_build_map,
            "can_avoid_obstacles": self.can_avoid_obstacles,
            "can_fly_warehouse_scan": self.can_fly_warehouse_scan,
            "can_build_warehouse_map": self.can_build_map,
            "missing_required_topics": list(self.missing_required_topics),
            "unhealthy_topics": list(self.unhealthy_topics),
            "missing_nvblox_topics": list(self.missing_nvblox_topics),
            "failure_code": self.failure_code,
            "user_message": self.user_message,
            "developer_message": self.developer_message,
            "suggested_actions": list(self.suggested_actions),
            "topic_diagnostics": self.topic_diagnostics,
            "health_sample_timestamp": self.health_sample_timestamp,
            "from_cache": self.from_cache,
            "probe_mode": self.probe_mode,
            "ready": self.ready,
        }

    def to_api_detail(self) -> dict[str, object]:
        return {
            "failure_code": self.failure_code,
            "severity": "error",
            "user_message": self.user_message,
            "developer_message": self.developer_message,
            "missing_topics": list(self.missing_required_topics),
            "unhealthy_topics": list(self.unhealthy_topics),
            "missing_nvblox_topics": list(self.missing_nvblox_topics),
            "suggested_actions": list(self.suggested_actions),
            "readiness": self.to_dict(),
        }


def readiness_from_perception_status_strict(
    status: WarehousePerceptionStatus,
    *,
    require_nvblox_for_map: bool = False,
) -> WarehouseReadinessResult:
    components = status.components if isinstance(status.components, dict) else {}
    capabilities = evaluate_warehouse_capabilities(
        status,
        require_nvblox_for_map=require_nvblox_for_map,
    )
    topic_diagnostics_raw = components.get("topic_diagnostics")
    topic_diagnostics = (
        topic_diagnostics_raw if isinstance(topic_diagnostics_raw, dict) else {}
    )

    missing: list[str] = []
    unhealthy: list[str] = []
    component_missing = _component_missing_required_topics(components)
    flight_topic_keys = ("visual_slam_odom", "depth", "rgb_image", "imu")
    if os.getenv("WAREHOUSE_REQUIRE_LOCAL_ODOMETRY", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        flight_topic_keys = (*flight_topic_keys, "local_odometry")
    if not capabilities["can_scan_lidar"]:
        flight_topic_keys = (*flight_topic_keys, "raw_lidar")

    for key in flight_topic_keys:
        diag = _topic_diag(components, key)
        cap_key = {
            "visual_slam_odom": "can_localize",
            "local_odometry": "can_localize",
            "depth": "can_perceive_depth",
            "rgb_image": "can_perceive_rgb",
            "raw_lidar": "can_scan_lidar",
            "imu": "can_perceive_imu",
        }[key]
        if capabilities.get(cap_key):
            continue
        if component_missing is not None and key not in component_missing:
            continue
        if diag is None or diag.get("readiness_state") == "topic_missing":
            missing.append(key)
        else:
            unhealthy.append(key)

    if not capabilities["can_localize"] and "visual_slam_odom" not in missing:
        if "visual_slam_odom" not in unhealthy and "local_odometry" not in unhealthy:
            unhealthy.append("visual_slam_odom")

    missing_nvblox = tuple(
        str(item) for item in (components.get("missing_nvblox_topics") or []) if item
    )

    failure_code: str | None = None
    if not status.reachable:
        failure_code = "bridge_unreachable"
    elif not capabilities["ros_graph_ready"]:
        failure_code = "ros_graph_unavailable"
    elif _gazebo_sim_enabled(components):
        gazebo_raw = components.get("gazebo")
        if isinstance(gazebo_raw, dict) and gazebo_raw.get("sim_publishing") is False:
            failure_code = "gazebo_sensors_idle"
    elif components.get("odometry_state_unreadable"):
        failure_code = "odometry_state_unreadable"
    elif not capabilities["can_localize"]:
        failure_code = "odometry_topic_unavailable"
    elif not capabilities["can_perceive_depth"]:
        failure_code = "depth_topic_unavailable"
    elif not capabilities["can_perceive_rgb"]:
        failure_code = "rgb_topic_unavailable"
    elif not capabilities["can_scan_lidar"]:
        failure_code = "raw_lidar_unavailable"
    elif require_nvblox_for_map and not capabilities["can_map_3d"]:
        failure_code = "nvblox_unavailable"
    elif not capabilities["can_fly_warehouse_scan"]:
        failure_code = "warehouse_sensors_not_ready"

    odom_topic = components.get("odometry_topic")
    if not isinstance(odom_topic, str) or not odom_topic.strip():
        vslam = _topic_diag(components, "visual_slam_odom")
        if isinstance(vslam, dict):
            odom_topic = vslam.get("matched") or vslam.get("expected")

    user_message = (
        user_message_for_failure(
            failure_code,
            missing_topics=tuple(missing),
            topic=str(odom_topic) if odom_topic else None,
        )
        if failure_code
        else None
    )
    developer_message = status.detail

    suggested: list[str] = []
    if not status.reachable:
        suggested.append("Ensure warehouse_bridge is running on WAREHOUSE_ROS_BRIDGE_URL")
    if missing or unhealthy:
        suggested.append("Press Play in Gazebo and verify: ros2 topic hz /warehouse/drone/odometry")
        suggested.append("Run scripts/check_warehouse_ros_health.sh")

    sample_ts_raw = components.get("health_sample_timestamp")
    health_sample_timestamp = (
        float(sample_ts_raw) if isinstance(sample_ts_raw, (int, float)) else time.time()
    )

    return WarehouseReadinessResult(
        bridge_alive=capabilities["bridge_alive"],
        ros_graph_ready=capabilities["ros_graph_ready"],
        can_localize=capabilities["can_localize"],
        can_perceive_depth=capabilities["can_perceive_depth"],
        can_perceive_rgb=capabilities["can_perceive_rgb"],
        can_scan_lidar=capabilities["can_scan_lidar"],
        can_build_map=capabilities["can_build_warehouse_map"],
        can_avoid_obstacles=capabilities["can_avoid_obstacles"],
        can_fly_warehouse_scan=capabilities["can_fly_warehouse_scan"],
        missing_required_topics=tuple(missing),
        unhealthy_topics=tuple(unhealthy),
        missing_nvblox_topics=missing_nvblox,
        failure_code=failure_code,
        user_message=user_message,
        developer_message=developer_message,
        suggested_actions=tuple(suggested),
        topic_diagnostics=topic_diagnostics,
        health_sample_timestamp=health_sample_timestamp,
        from_cache=bool(components.get("from_cache", False)),
        probe_mode=str(components.get("probe_mode") or "") or None,
    )

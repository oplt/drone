from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable, Sequence
from math import atan, pi, radians, tan
from typing import Any

from shapely.geometry import LineString, Point, Polygon

from backend.core.config.runtime import env_truthy, settings
from backend.modules.missions.schemas.mission_types import (
    AdaptiveAltitudeMission,
    GridMission,
    IndoorExplorationMission,
    OrbitMission,
    PerimeterPatrolMission,
    TerrainFollowMission,
    WarehouseScanMission,
    Waypoint,
)
from backend.modules.preflight.range_estimator import SimpleWhPerKmModel
from backend.modules.vehicle_runtime.types import Coordinate

from ..context import PreflightContext
from ..schemas import CheckResult, CheckStatus
from .base import MissionPreflightBase, warehouse_sim_mode

class WarehouseScanMissionPreflight(MissionPreflightBase):
    """Indoor warehouse scan checks for local-frame navigation and corridor geometry."""

    def __init__(self, context: PreflightContext):
        super().__init__(context)
        self.mission: WarehouseScanMission = context.mission

    def check_local_origin(self) -> CheckResult:
        origin = getattr(self.mission, "local_origin", None)
        if origin is None:
            return CheckResult(
                name="Warehouse Local Origin",
                status=CheckStatus.FAIL,
                message="No local warehouse origin was defined",
            )
        lat = getattr(origin, "lat", None)
        lon = getattr(origin, "lon", None)
        if lat is None or lon is None:
            return CheckResult(
                name="Warehouse Local Origin",
                status=CheckStatus.PASS,
                message="Origin defined in local warehouse frame",
            )
        return CheckResult(
            name="Warehouse Local Origin",
            status=CheckStatus.PASS,
            message=f"Origin locked at ({float(lat):.6f}, {float(lon):.6f})",
        )

    def _perception_status(self) -> dict[str, Any]:
        status = self.ctx.config_overrides.get("WAREHOUSE_PERCEPTION_STATUS")
        return status if isinstance(status, dict) else {}

    def _perception_components(self) -> dict[str, Any]:
        components = self._perception_status().get("components")
        return components if isinstance(components, dict) else {}

    def _component_bool(self, *keys: str) -> bool | None:
        components = self._perception_components()
        for key in keys:
            value = components.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, dict):
                nested = value.get("ready", value.get("healthy", value.get("ok")))
                if isinstance(nested, bool):
                    return nested
        return None

    def _topic_configured(self, *keys: str) -> bool:
        topics = self._perception_components().get("topics")
        if not isinstance(topics, dict):
            return False
        for key in keys:
            topic = topics.get(key)
            if not isinstance(topic, str) or not topic.strip():
                return False
        return True

    def _component_check(
        self,
        *,
        name: str,
        keys: tuple[str, ...],
        pass_message: str,
        fail_message: str,
    ) -> CheckResult:
        value = self._component_bool(*keys)
        if value is True:
            return CheckResult(name=name, status=CheckStatus.PASS, message=pass_message)
        if value is False:
            return CheckResult(name=name, status=CheckStatus.FAIL, message=fail_message)
        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=f"{name} status is missing from the ROS bridge health payload",
        )

    def _topic_diagnostic(self, key: str) -> dict[str, Any] | None:
        components = self._perception_components()
        diagnostics = components.get("topic_diagnostics")
        if isinstance(diagnostics, dict):
            diag = diagnostics.get(key)
            if isinstance(diag, dict):
                return diag
        matches = components.get("topic_matches")
        if isinstance(matches, dict):
            diag = matches.get(key)
            if isinstance(diag, dict):
                return diag
        return None

    def _topic_diagnostic_message(self, key: str) -> str | None:
        diag = self._topic_diagnostic(key)
        if not diag:
            return None
        expected = diag.get("expected")
        matched = diag.get("matched")
        error = diag.get("error")
        if error:
            return f"expected={expected} matched={matched or 'none'} ({error})"
        if not diag.get("healthy"):
            return f"expected={expected} matched={matched or 'none'}"
        return None

    def _tf_chain_detail(self) -> str | None:
        components = self._perception_components()
        tf_chain = components.get("tf_chain")
        if isinstance(tf_chain, dict):
            detail = tf_chain.get("detail")
            if isinstance(detail, str) and detail.strip() and detail != "ok":
                return detail.strip()
        return None

    def _missing_topics_message(self, *, prefix: str) -> str:
        components = self._perception_components()
        missing = components.get("missing_required_topics")
        if isinstance(missing, list) and missing:
            return f"{prefix}: {', '.join(str(item) for item in missing)}"
        detail = self._perception_status().get("detail")
        if isinstance(detail, str) and detail.strip():
            return f"{prefix}. {detail.strip()}"
        return prefix

    def _warehouse_sensor_readiness(self):
        status_dict = self._perception_status()
        if not status_dict:
            return None

        class _Readiness:
            ready = bool(status_dict.get("ready"))
            detail = status_dict.get("detail") if isinstance(status_dict.get("detail"), str) else None

        return _Readiness()

    def check_ros_bridge(self) -> CheckResult:
        status = self._perception_status()
        if not status:
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.FAIL,
                message="Warehouse ROS bridge health was not collected",
            )
        if not bool(status.get("configured")):
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.FAIL,
                message="Warehouse ROS bridge URL is not configured",
            )
        if not bool(status.get("reachable")):
            detail = status.get("detail")
            suffix = f": {detail}" if isinstance(detail, str) and detail else ""
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.FAIL,
                message=f"Jetson ROS bridge is unreachable{suffix}",
            )
        if bool(status.get("ready")):
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.PASS,
                message=f"Jetson bridge ready ({status.get('profile') or 'unknown profile'})",
            )
        takeoff = self._warehouse_sensor_readiness()
        if takeoff is not None and takeoff.ready:
            return CheckResult(
                name="Warehouse ROS Bridge",
                status=CheckStatus.PASS,
                message=(
                    f"Bridge reachable; required sensor topics are live "
                    f"({status.get('profile') or 'unknown profile'})"
                ),
            )
        bridge_status = status.get("status") or "not ready"
        detail = takeoff.detail if takeoff is not None and takeoff.detail else None
        prefix = f"Jetson ROS bridge status is {bridge_status}"
        if detail:
            prefix = f"{prefix}: {detail}"
        return CheckResult(
            name="Warehouse ROS Bridge",
            status=CheckStatus.FAIL,
            message=self._missing_topics_message(prefix=prefix),
        )

    def check_ros_graph(self) -> CheckResult:
        value = self._component_bool("ros_graph", "ros2_graph", "ros2_cli")
        if value is True:
            return CheckResult(
                name="Warehouse ROS Graph",
                status=CheckStatus.PASS,
                message="ROS 2 graph is available",
            )
        if value is False:
            return CheckResult(
                name="Warehouse ROS Graph",
                status=CheckStatus.FAIL,
                message="ROS 2 graph or ros2 CLI is unavailable on the Jetson",
            )
        return CheckResult(
            name="Warehouse ROS Graph",
            status=CheckStatus.FAIL,
            message="ROS 2 graph health is missing from the bridge payload",
        )

    def check_camera_topics(self) -> CheckResult:
        if self._component_bool("camera_topics", "stereo_camera") is True:
            return CheckResult(
                name="Warehouse Camera Topics",
                status=CheckStatus.PASS,
                message="Camera topics are publishing",
            )
        rgb_diag = self._topic_diagnostic("rgb_image")
        if rgb_diag and (
            rgb_diag.get("healthy")
            or rgb_diag.get("readiness_state") in {"ok", "ok_via_messages", "shallow_present"}
        ):
            matched = rgb_diag.get("matched") or rgb_diag.get("expected")
            return CheckResult(
                name="Warehouse Camera Topics",
                status=CheckStatus.PASS,
                message=f"RGB camera topic listed ({matched})",
            )
        detail = self._topic_diagnostic_message("rgb_image")
        if detail is None:
            left_detail = self._topic_diagnostic_message("left_image")
            right_detail = self._topic_diagnostic_message("right_image")
            if left_detail or right_detail:
                detail = "; ".join(filter(None, [left_detail, right_detail]))
        return CheckResult(
            name="Warehouse Camera Topics",
            status=CheckStatus.FAIL,
            message=detail or "RGB or stereo camera topics are not publishing",
        )

    def check_stereo_sync(self) -> CheckResult:
        value = self._component_bool("stereo_sync", "stereo_timestamps_synced")
        if value is True:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.PASS,
                message="Stereo timestamps are synchronized",
            )
        if value is False:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.FAIL,
                message="Stereo timestamps are not synchronized",
            )

        rgb_diag = self._topic_diagnostic("rgb_image")
        rgb_ok = bool(
            rgb_diag
            and (
                rgb_diag.get("healthy")
                or rgb_diag.get("readiness_state")
                in {"ok", "ok_via_messages", "ok_graph_presence", "shallow_present"}
            )
        )
        left_diag = self._topic_diagnostic("left_image")
        right_diag = self._topic_diagnostic("right_image")
        stereo_topics_present = bool(left_diag or right_diag)

        if rgb_ok and not stereo_topics_present:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.SKIP,
                message="RGBD front camera in use; stereo pair sync not required",
            )

        if rgb_ok:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.PASS,
                message="RGB camera live; stereo sync not reported (RGBD mode)",
            )

        sim_mode = _warehouse_sim_mode()
        if sim_mode:
            return CheckResult(
                name="Warehouse Stereo Sync",
                status=CheckStatus.WARN,
                message=(
                    "Stereo sync not reported by bridge; verify left/right topics if using stereo"
                ),
            )

        return CheckResult(
            name="Warehouse Stereo Sync",
            status=CheckStatus.FAIL,
            message="Warehouse Stereo Sync status is missing from the ROS bridge health payload",
        )

    def check_imu_topic(self) -> CheckResult:
        if self._component_bool("imu_healthy", "imu_topic", "imu") is True:
            return CheckResult(
                name="Warehouse IMU Topic",
                status=CheckStatus.PASS,
                message="IMU topic is publishing",
            )
        detail = self._topic_diagnostic_message("imu")
        return CheckResult(
            name="Warehouse IMU Topic",
            status=CheckStatus.FAIL,
            message=detail or "IMU topic is not publishing",
        )

    def check_tf_tree(self) -> CheckResult:
        if self._component_bool("tf_tree", "tf", "tf_static") is True:
            return CheckResult(
                name="Warehouse TF Tree",
                status=CheckStatus.PASS,
                message="Required TF chain odom→base_link→camera is valid",
            )
        detail = self._tf_chain_detail()
        return CheckResult(
            name="Warehouse TF Tree",
            status=CheckStatus.FAIL,
            message=detail or "Required TF frames are missing or disconnected (odom/base_link/camera)",
        )

    def check_visual_slam(self) -> CheckResult:
        if self._component_bool(
            "visual_slam_healthy",
            "visual_slam",
            "vslam",
            "visual_slam_tracking",
        ):
            return CheckResult(
                name="Warehouse Visual SLAM",
                status=CheckStatus.PASS,
                message="Visual SLAM odometry is publishing and fresh",
            )
        if self._component_bool("odometry_state_unreadable"):
            topic = self._perception_components().get("odometry_topic") or "/warehouse/drone/odometry"
            return CheckResult(
                name="Warehouse Local Odometry",
                status=CheckStatus.FAIL,
                message=(
                    f"Local odometry state unreadable; verify publishing on {topic} "
                    "(single-message sensor sample)"
                ),
            )
        for key in ("visual_slam_odom", "local_odometry"):
            diag = self._topic_diagnostic(key)
            if diag and (
                diag.get("healthy")
                or diag.get("readiness_state") in {"ok", "ok_via_messages", "shallow_present"}
            ):
                matched = diag.get("matched") or diag.get("expected")
                source = self._perception_components().get("odometry_source") or "local_odom"
                return CheckResult(
                    name="Warehouse Local Odometry",
                    status=CheckStatus.PASS,
                    message=f"{source} live ({matched})",
                )
        detail = self._topic_diagnostic_message("visual_slam_odom")
        topic = self._perception_components().get("odometry_topic") or "/warehouse/drone/odometry"
        return CheckResult(
            name="Warehouse Local Odometry",
            status=CheckStatus.FAIL,
            message=detail or f"Local odometry not ready (check {topic})",
        )

    def check_nvblox(self) -> CheckResult:
        if self._component_bool("nvblox_healthy", "nvblox", "nvblox_mapping"):
            return CheckResult(
                name="Warehouse Nvblox",
                status=CheckStatus.PASS,
                message="Nvblox mapping outputs are publishing and fresh",
            )
        components = self._perception_components()
        sim_mode = _warehouse_sim_mode()
        listed = components.get("listed_topics")
        has_nvblox_node = isinstance(listed, list) and any(
            str(topic).startswith("/nvblox_node/") for topic in listed
        )
        if components.get("nvblox_warming_up") or (sim_mode and has_nvblox_node):
            return CheckResult(
                name="Warehouse Nvblox",
                status=CheckStatus.WARN,
                message=(
                    "Nvblox is running; map outputs may still be warming up — "
                    "flight can start mapping in parallel"
                ),
            )
        strict_nvblox = env_truthy(settings.warehouse_preflight_wait_nvblox)
        if sim_mode and not has_nvblox_node and not strict_nvblox:
            return CheckResult(
                name="Warehouse Nvblox",
                status=CheckStatus.WARN,
                message=(
                    "Nvblox is not running yet (starts when the warehouse flight begins); "
                    "Source transport sensor topics are sufficient for preflight"
                ),
            )
        missing = components.get("missing_nvblox_topics")
        detail_parts: list[str] = []
        if isinstance(missing, list) and missing:
            detail_parts.append(f"missing outputs: {', '.join(str(item) for item in missing)}")
        for key in ("pointcloud", "mesh", "mesh_marker", "occupancy", "esdf", "back_projected_depth"):
            diag_msg = self._topic_diagnostic_message(key)
            if diag_msg:
                detail_parts.append(f"{key}: {diag_msg}")
        return CheckResult(
            name="Warehouse Nvblox",
            status=CheckStatus.FAIL,
            message="; ".join(detail_parts) or "Nvblox mapping outputs are not ready",
        )

    def check_mapping_disk(self) -> CheckResult:
        components = self._perception_components()
        min_gb = float(self._thr("WAREHOUSE_MAPPING_DISK_FREE_GB_MIN", 10.0))
        raw_gb = components.get("disk_free_gb")
        if raw_gb is None and components.get("disk_free_bytes") is not None:
            raw_gb = float(components["disk_free_bytes"]) / 1_000_000_000.0
        if raw_gb is None:
            disk = components.get("disk")
            if isinstance(disk, dict):
                raw_gb = disk.get("free_gb")
        if raw_gb is None:
            return CheckResult(
                name="Warehouse Mapping Disk",
                status=CheckStatus.FAIL,
                message="Free capture disk space is missing from ROS bridge health",
            )
        free_gb = float(raw_gb)
        if free_gb < min_gb:
            return CheckResult(
                name="Warehouse Mapping Disk",
                status=CheckStatus.FAIL,
                message=f"Capture disk free {free_gb:.1f}GB < required {min_gb:.1f}GB",
            )
        return CheckResult(
            name="Warehouse Mapping Disk",
            status=CheckStatus.PASS,
            message=f"Capture disk free {free_gb:.1f}GB",
        )

    def check_sensor_rig(self) -> CheckResult:
        sensor_rig_id = getattr(self.mission, "sensor_rig_id", None)
        if sensor_rig_id is None:
            return CheckResult(
                name="Warehouse Sensor Rig",
                status=CheckStatus.FAIL,
                message="No calibrated sensor rig was selected for this scan",
            )
        return CheckResult(
            name="Warehouse Sensor Rig",
            status=CheckStatus.PASS,
            message=f"Sensor rig {sensor_rig_id} selected",
        )

    def check_battery_margin(self) -> CheckResult:
        reserve_pct = float(self._thr("WAREHOUSE_SCAN_BATTERY_RESERVE_PCT", 30.0))
        if reserve_pct <= 0:
            return CheckResult(
                name="Warehouse Battery Margin",
                status=CheckStatus.SKIP,
                message="Battery margin check disabled for ROS/sim warehouse preflight",
            )
        battery_pct = getattr(self.v, "battery_percent", None)
        if battery_pct is None:
            battery_pct = getattr(self.v, "battery_remaining", None)
        if battery_pct is None:
            return CheckResult(
                name="Warehouse Battery Margin",
                status=CheckStatus.SKIP,
                message="Battery percentage unavailable (MAVLink not required for warehouse sim)",
            )
        pct = float(battery_pct)
        if pct <= 1.0:
            pct *= 100.0
        if pct < reserve_pct:
            return CheckResult(
                name="Warehouse Battery Margin",
                status=CheckStatus.FAIL,
                message=f"Battery {pct:.0f}% < warehouse reserve {reserve_pct:.0f}%",
            )
        return CheckResult(
            name="Warehouse Battery Margin",
            status=CheckStatus.PASS,
            message=f"Battery {pct:.0f}% >= reserve {reserve_pct:.0f}%",
        )

    def check_dock_marker(self) -> CheckResult:
        marker_id = getattr(self.mission, "dock_marker_id", None)
        precision_required = bool(getattr(self.mission, "dock_precision_required", False))
        if not marker_id and not precision_required:
            return CheckResult(
                name="Warehouse Dock Marker",
                status=CheckStatus.SKIP,
                message="No precision dock marker required for this scan",
            )
        visible = self._component_bool("dock_marker", "apriltag", "dock_reference")
        if visible is True:
            return CheckResult(
                name="Warehouse Dock Marker",
                status=CheckStatus.PASS,
                message=f"Dock marker {marker_id or ''} visible".strip(),
            )
        if visible is False:
            return CheckResult(
                name="Warehouse Dock Marker",
                status=CheckStatus.FAIL,
                message="Required dock marker is not visible",
            )
        return CheckResult(
            name="Warehouse Dock Marker",
            status=CheckStatus.FAIL,
            message="Required dock marker visibility is missing from ROS bridge health",
        )

    def check_local_position_lock(self) -> CheckResult:
        local_ok = getattr(self.v, "local_position_ok", None)
        if local_ok is True:
            return CheckResult(
                name="Warehouse Local Position",
                status=CheckStatus.PASS,
                message="Vehicle local position is available",
            )
        if local_ok is False:
            return CheckResult(
                name="Warehouse Local Position",
                status=CheckStatus.FAIL,
                message="Vehicle local position is unavailable",
            )
        north = getattr(self.v, "local_north_m", None)
        east = getattr(self.v, "local_east_m", None)
        down = getattr(self.v, "local_down_m", None)
        if north is not None and east is not None and down is not None:
            return CheckResult(
                name="Warehouse Local Position",
                status=CheckStatus.PASS,
                message="Vehicle local position is populated",
            )
        return CheckResult(
            name="Warehouse Local Position",
            status=CheckStatus.FAIL,
            message="Warehouse missions require a valid local frame before launch",
        )

    def check_odometry_health(self) -> CheckResult:
        odometry_healthy = getattr(self.v, "odometry_healthy", None)
        max_drift_m = float(self._thr("WAREHOUSE_ODOMETRY_DRIFT_MAX_M", 0.75))
        drift_m = getattr(self.v, "odometry_drift_m", None)
        if odometry_healthy is False:
            return CheckResult(
                name="Warehouse Odometry",
                status=CheckStatus.FAIL,
                message="Vehicle odometry is unhealthy",
            )
        if drift_m is not None and float(drift_m) > max_drift_m:
            return CheckResult(
                name="Warehouse Odometry",
                status=CheckStatus.FAIL,
                message=f"Odometry drift {float(drift_m):.2f}m > {max_drift_m:.2f}m",
            )
        if odometry_healthy is True or drift_m is not None:
            detail = f"Drift {float(drift_m):.2f}m" if drift_m is not None else "Odometry healthy"
            return CheckResult(
                name="Warehouse Odometry",
                status=CheckStatus.PASS,
                message=detail,
            )
        return CheckResult(
            name="Warehouse Odometry",
            status=CheckStatus.WARN,
            message="Odometry health could not be verified from telemetry",
        )

    def check_lidar_health(self) -> CheckResult:
        components = self._perception_components()
        raw_lidar_healthy = components.get("raw_lidar_healthy")
        from backend.modules.warehouse.service.live_map_config import (
            persist_raw_lidar_layer,
            raw_lidar_enabled,
        )

        raw_lidar_required = raw_lidar_enabled() or persist_raw_lidar_layer()
        if raw_lidar_healthy is True:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.PASS,
                message="LiDAR point cloud topic is publishing",
            )
        if raw_lidar_healthy is False and raw_lidar_required:
            detail = self._topic_diagnostic_message("raw_lidar")
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message=detail or "LiDAR point cloud topic is not publishing",
            )

        lidar_healthy = getattr(self.v, "lidar_healthy", None)
        obstacle_distance_m = getattr(self.v, "obstacle_distance_m", None)
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))
        if lidar_healthy is False:
            if not raw_lidar_required:
                return CheckResult(
                    name="Warehouse LiDAR",
                    status=CheckStatus.SKIP,
                    message="Raw LiDAR live-map layer is disabled for this scan",
                )
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message="LiDAR/range input is unhealthy",
            )
        if obstacle_distance_m is not None and float(obstacle_distance_m) < clearance_m:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.FAIL,
                message=(
                    f"Obstacle distance {float(obstacle_distance_m):.2f}m is inside "
                    f"the required clearance {clearance_m:.2f}m"
                ),
            )
        if lidar_healthy is True:
            message = (
                f"Obstacle distance {float(obstacle_distance_m):.2f}m"
                if obstacle_distance_m is not None
                else "Range stream healthy"
            )
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.PASS,
                message=message,
            )
        if not raw_lidar_required:
            return CheckResult(
                name="Warehouse LiDAR",
                status=CheckStatus.SKIP,
                message="Raw LiDAR live-map layer is disabled for this scan",
            )
        detail = self._topic_diagnostic_message("raw_lidar")
        return CheckResult(
            name="Warehouse LiDAR",
            status=CheckStatus.FAIL,
            message=detail or "LiDAR/range health is unknown; raw_lidar topic not publishing",
        )

    def check_scan_layers(self) -> CheckResult:
        layers = list(getattr(self.mission, "scan_layers", []) or [])
        if not layers:
            return CheckResult(
                name="Warehouse Scan Layers",
                status=CheckStatus.FAIL,
                message="No scan layers were generated",
            )
        top_z = max(float(layer.z_m) for layer in layers)
        ceiling_height = getattr(self.mission, "ceiling_height_m", None)
        ceiling_margin = float(getattr(self.mission, "ceiling_margin_m", 0.0))
        if ceiling_height is not None and top_z + ceiling_margin > float(ceiling_height):
            return CheckResult(
                name="Warehouse Scan Layers",
                status=CheckStatus.FAIL,
                message=(
                    f"Top scan layer {top_z:.2f}m plus margin {ceiling_margin:.2f}m "
                    f"exceeds ceiling {float(ceiling_height):.2f}m"
                ),
            )
        ceiling_distance = getattr(self.v, "ceiling_distance_m", None)
        if ceiling_distance is not None and float(ceiling_distance) < ceiling_margin:
            return CheckResult(
                name="Warehouse Scan Layers",
                status=CheckStatus.FAIL,
                message=(
                    f"Measured ceiling distance {float(ceiling_distance):.2f}m is below "
                    f"required margin {ceiling_margin:.2f}m"
                ),
            )
        return CheckResult(
            name="Warehouse Scan Layers",
            status=CheckStatus.PASS,
            message=f"{len(layers)} layers, top altitude {top_z:.2f}m",
        )

    def check_corridor_geometry(self) -> CheckResult:
        corridors = list(getattr(self.mission, "corridors", []) or [])
        if not corridors:
            return CheckResult(
                name="Warehouse Corridors",
                status=CheckStatus.FAIL,
                message="No warehouse corridors were generated",
            )
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))
        narrow = []
        short = []
        for corridor in corridors:
            start = corridor.start
            end = corridor.end
            length_m = math.hypot(end.x_m - start.x_m, end.y_m - start.y_m)
            if float(corridor.width_m) < clearance_m * 2.0:
                narrow.append(corridor.corridor_id)
            if length_m < clearance_m * 2.0:
                short.append(corridor.corridor_id)
        if narrow:
            return CheckResult(
                name="Warehouse Corridors",
                status=CheckStatus.FAIL,
                message=f"Corridors too narrow for clearance: {', '.join(narrow[:5])}",
            )
        if short:
            return CheckResult(
                name="Warehouse Corridors",
                status=CheckStatus.FAIL,
                message=f"Corridors too short for stable scan passes: {', '.join(short[:5])}",
            )
        return CheckResult(
            name="Warehouse Corridors",
            status=CheckStatus.PASS,
            message=f"{len(corridors)} corridors satisfy clearance and length checks",
        )

    def check_keepout_conflicts(self) -> CheckResult:
        keepouts = list(getattr(self.mission, "keepout_zones", []) or [])
        obstacles = list(getattr(self.mission, "obstacles_3d", []) or [])
        corridors = list(getattr(self.mission, "corridors", []) or [])
        clearance_m = float(getattr(self.mission, "clearance_m", 0.6))

        if not keepouts and not obstacles:
            return CheckResult(
                name="Warehouse Keepouts",
                status=CheckStatus.PASS,
                message="No keepout or obstacle conflicts were declared",
            )

        corridor_geoms = [
            LineString(
                [
                    (float(c.start.x_m), float(c.start.y_m)),
                    (float(c.end.x_m), float(c.end.y_m)),
                ]
            ).buffer(clearance_m)
            for c in corridors
        ]
        for zone in keepouts:
            zone_poly = Polygon([(pt.x_m, pt.y_m) for pt in zone.footprint])
            for geom in corridor_geoms:
                if geom.intersects(zone_poly):
                    return CheckResult(
                        name="Warehouse Keepouts",
                        status=CheckStatus.FAIL,
                        message=f"Corridor path intersects keepout zone '{zone.zone_id}'",
                    )
        for obstacle in obstacles:
            half_x = float(obstacle.size_x_m) / 2.0
            half_y = float(obstacle.size_y_m) / 2.0
            obstacle_poly = Point(
                float(obstacle.center.x_m),
                float(obstacle.center.y_m),
            ).buffer(max(half_x, half_y), cap_style=3)
            for geom in corridor_geoms:
                if geom.intersects(obstacle_poly):
                    return CheckResult(
                        name="Warehouse Keepouts",
                        status=CheckStatus.FAIL,
                        message=f"Corridor path intersects obstacle '{obstacle.obstacle_id}'",
                    )
        return CheckResult(
            name="Warehouse Keepouts",
            status=CheckStatus.PASS,
            message="Corridors clear all declared keepouts and obstacles",
        )

    async def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        results.append(self.check_waypoint_count_limit())
        results.append(self.check_speed_limits())
        results.append(self.check_local_origin())
        results.append(self.check_local_position_lock())
        results.append(self.check_ros_bridge())
        results.append(self.check_ros_graph())
        results.append(self.check_camera_topics())
        results.append(self.check_stereo_sync())
        results.append(self.check_imu_topic())
        results.append(self.check_tf_tree())
        results.append(self.check_visual_slam())
        results.append(self.check_nvblox())
        results.append(self.check_mapping_disk())
        results.append(self.check_sensor_rig())
        results.append(self.check_battery_margin())
        results.append(self.check_dock_marker())
        results.append(self.check_odometry_health())
        results.append(self.check_lidar_health())
        results.append(self.check_scan_layers())
        results.append(self.check_corridor_geometry())
        results.append(self.check_keepout_conflicts())
        return results



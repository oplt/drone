from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from pathlib import Path
from typing import Any

from .config import BridgeConfig, topic_aliases, topic_env, topic_registry
from .topic_diagnostics import (
    probe_gazebo_sensors,
    probe_topics,
    summarize_diagnostics,
)

logger = logging.getLogger(__name__)

_ARTIFACT_EXTENSIONS = {
    ".glb",
    ".gltf",
    ".obj",
    ".ply",
    ".pcd",
    ".las",
    ".laz",
    ".e57",
    ".db3",
    ".mcap",
    ".bag",
    ".tsdf",
    ".esdf",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_token(value: object) -> str:
    raw = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or ""))
    return raw.strip("._-") or "unknown"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def mapping_session_active_path(capture_root: Path) -> Path:
    override = os.getenv("WAREHOUSE_MAPPING_SESSION_ACTIVE_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return capture_root / ".mapping_session_active"


def mark_mapping_session_active(capture_root: Path, flight_id: str) -> None:
    path = mapping_session_active_path(capture_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(flight_id.strip(), encoding="utf-8")


def clear_mapping_session_active(capture_root: Path) -> None:
    path = mapping_session_active_path(capture_root)
    if path.exists():
        path.unlink()


@dataclass
class MappingSession:
    flight_id: str
    warehouse_map_id: int | None
    profile: str
    session_dir: Path
    started_at: str = field(default_factory=utc_now_iso)
    stopped_at: str | None = None
    launch_pid: int | None = None
    status: str = "running"

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "warehouse_mapping_manifest.json"

    def to_manifest(self) -> dict[str, Any]:
        return {
            "flight_id": self.flight_id,
            "warehouse_map_id": self.warehouse_map_id,
            "profile": self.profile,
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "session_dir": str(self.session_dir),
            "launch_pid": self.launch_pid,
            "topics": topic_env(),
        }


class BridgeState:
    TOPIC_CACHE_GRACE_S = 30.0
    TOPIC_PROBE_ATTEMPTS = 3

    HEALTH_CACHE_TTL_S = 5.0
    FAST_HEALTH_CACHE_S = 1.0
    TF_PROBE_INTERVAL_S = 15.0
    TOPIC_FAST_CACHE_S = 5.0
    DEEP_HEALTH_STALE_S = 20.0
    DEEP_REFRESH_INTERVAL_S = 8.0

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.config.capture_root.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, MappingSession] = {}
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self._last_nonempty_topics: set[str] | None = None
        self._last_nonempty_topics_at = 0.0
        self._last_probe_error: str | None = None
        self._last_health_signature: tuple[object, ...] | None = None
        self._health_cache: tuple[float, dict[str, Any]] | None = None
        self._deep_health_cache: tuple[float, dict[str, Any]] | None = None
        self._health_lock = threading.Lock()
        self._last_tf_probe_at = 0.0
        self._last_tf_probe_result: object | None = None
        if self._background_probe_enabled():
            threading.Thread(
                target=self._deep_health_refresh_loop,
                daemon=True,
                name="warehouse-health-probe",
            ).start()

    @staticmethod
    def _background_probe_enabled() -> bool:
        raw = os.getenv("WAREHOUSE_HEALTH_BACKGROUND_PROBE", "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _deep_probe_enabled() -> bool:
        raw = os.getenv("WAREHOUSE_HEALTH_DEEP_PROBE", "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _deep_health_refresh_loop(self) -> None:
        interval_s = float(
            os.getenv("WAREHOUSE_HEALTH_REFRESH_INTERVAL_S", str(self.DEEP_REFRESH_INTERVAL_S))
        )
        while True:
            try:
                payload = self._build_health(deep=True)
                with self._health_lock:
                    self._deep_health_cache = (monotonic(), payload)
            except Exception:
                logger.exception("Warehouse deep health refresh failed")
            time.sleep(max(1.0, interval_s))

    def health(self, *, deep: bool = False) -> dict[str, Any]:
        if deep:
            payload = self._build_health(deep=True)
            with self._health_lock:
                self._deep_health_cache = (monotonic(), payload)
            payload = dict(payload)
            payload["probe_mode"] = "deep"
            return payload

        stale_s = float(os.getenv("WAREHOUSE_HEALTH_DEEP_STALE_S", str(self.DEEP_HEALTH_STALE_S)))
        with self._health_lock:
            if self._deep_health_cache is not None:
                cached_at, cached_payload = self._deep_health_cache
                age_s = monotonic() - cached_at
                if age_s <= stale_s:
                    payload = dict(cached_payload)
                    payload["probe_mode"] = "deep_cached"
                    payload["probe_age_s"] = round(age_s, 2)
                    return payload

        now = monotonic()
        if self._health_cache is not None:
            cached_at, cached_payload = self._health_cache
            if now - cached_at <= self.FAST_HEALTH_CACHE_S:
                return cached_payload

        payload = self._build_health(deep=False)
        payload = dict(payload)
        payload["probe_mode"] = "shallow"
        self._health_cache = (now, payload)
        return payload

    def _build_health(self, *, deep: bool) -> dict[str, Any]:
        registry = topic_registry()
        topics = topic_env()
        listed_topics = self._stable_ros2_topics(fast=not deep)
        disk = shutil.disk_usage(self.config.capture_root)
        odometry_state = self._read_odometry_state()

        probe_keys = sorted(
            set(registry.required_for_perception)
            | set(registry.required_for_nvblox_any)
            | {"left_image", "right_image", "mesh"}
        )
        deep_probe = deep or self._deep_probe_enabled()
        if deep_probe:
            diagnostics = probe_topics(listed_topics, keys=probe_keys)
        else:
            diagnostics = {
                key: self._shallow_topic_diagnostic(key, topics.get(key, ""), listed_topics)
                for key in probe_keys
                if topics.get(key)
            }

        summary = summarize_diagnostics(diagnostics)
        topic_health = {key: diag.healthy for key, diag in diagnostics.items()}
        topic_presence = {key: diag.listed or diag.publisher_count > 0 for key, diag in diagnostics.items()}

        rgb_ok = topic_health.get("rgb_image", False)
        left_ok = topic_health.get("left_image", False)
        right_ok = topic_health.get("right_image", False)
        camera_ready = rgb_ok or (left_ok and right_ok)

        vslam_diag = diagnostics.get("visual_slam_odom")
        local_odom_diag = diagnostics.get("local_odometry")
        imu_diag = diagnostics.get("imu")
        vslam_ready = bool(vslam_diag and vslam_diag.healthy)
        local_odom_ready = bool(local_odom_diag and local_odom_diag.healthy)

        nvblox_ready = any(
            topic_health.get(key, False)
            for key in registry.required_for_nvblox_any
        )
        ros_graph_ready = listed_topics is not None and len(listed_topics) > 0

        missing_required = [
            key
            for key in summary["missing_required_topics"]
            if key not in {"rgb_image", "left_image", "right_image"}
        ]
        if not camera_ready:
            missing_required.append("rgb_image")
        missing_nvblox = list(summary["missing_nvblox_topics"])

        gazebo_status = None
        if registry.profile == "gazebo" and deep:
            gazebo_status = probe_gazebo_sensors()

        if deep:
            tf_diag = self._cached_tf_chain_probe()
        else:
            tf_diag = self._tf_from_deep_cache()
        tf_tree = tf_diag.chain_ok if tf_diag is not None else False
        override_tf = self._optional_bool_env("WAREHOUSE_TF_TREE_OK")
        if override_tf is not None:
            tf_tree = override_tf

        stereo_sync = self._optional_bool_env("WAREHOUSE_STEREO_SYNC_OK")
        if stereo_sync is None and left_ok and right_ok:
            stereo_sync = True

        perception_ready = bool(
            ros_graph_ready
            and camera_ready
            and topic_health.get("depth", False)
            and topic_health.get("imu", False)
            and topic_health.get("raw_lidar", False)
            and vslam_ready
            and local_odom_ready
            and tf_tree
        )

        health_detail = self._format_health_detail(
            missing_required=missing_required,
            missing_nvblox=missing_nvblox,
            nvblox_ready=nvblox_ready,
            summary=summary,
            tf_detail=(
                tf_diag.detail
                if tf_diag
                else ("tf diagnostics pending" if not deep else "tf probe unavailable")
            ),
            gazebo=gazebo_status if registry.profile == "gazebo" else None,
        )

        self._log_health_change(
            ros_graph_ready=ros_graph_ready,
            ready=perception_ready,
            topic_count=len(listed_topics) if listed_topics is not None else None,
            missing_required=missing_required,
            missing_nvblox=missing_nvblox,
            probe_error=self._last_probe_error,
            topic_matches=summary.get("topic_matches", {}),
        )
        diagnostics_payload = {key: diag.to_dict() for key, diag in diagnostics.items()}
        return {
            "status": "ready" if perception_ready else "degraded",
            "ready": perception_ready,
            "detail": health_detail,
            "profile": self.config.profile,
            "topic_profile": registry.profile,
            "capture_root": str(self.config.capture_root),
            "websocket_url": self.config.ros_ws_url,
            "components": {
                "ros2_cli": bool(shutil.which("ros2")),
                "ros_graph": ros_graph_ready,
                "autolaunch": self.config.autolaunch,
                "active_sessions": len(self.sessions),
                "topics": topics,
                "listed_topics": sorted(listed_topics) if listed_topics is not None else [],
                "ros_topic_count": len(listed_topics) if listed_topics is not None else 0,
                "ros_topic_probe_error": self._last_probe_error,
                "missing_required_topics": missing_required,
                "missing_nvblox_topics": missing_nvblox,
                "topic_presence": topic_presence,
                "topic_diagnostics": diagnostics_payload,
                "topic_matches": summary.get("topic_matches", {}),
                "camera_topics": camera_ready,
                "imu_topic": bool(imu_diag and imu_diag.healthy),
                "imu_healthy": bool(imu_diag and imu_diag.healthy),
                "raw_lidar_healthy": bool(
                    diagnostics.get("raw_lidar") and diagnostics["raw_lidar"].healthy
                ),
                "visual_slam": vslam_ready,
                "vslam": vslam_ready,
                "visual_slam_tracking": vslam_ready,
                "visual_slam_healthy": vslam_ready,
                "local_odometry_healthy": local_odom_ready,
                "local_position_ok": bool(odometry_state.get("local_position_ok", False)),
                "slam_ready": vslam_ready and bool(odometry_state.get("slam_ready", True)),
                "slam_tracking_ok": vslam_ready and bool(odometry_state.get("slam_tracking_ok", True)),
                "localization_confidence": odometry_state.get("localization_confidence"),
                "odometry_drift_m": odometry_state.get("odometry_drift_m"),
                "local_odometry_state": odometry_state,
                "nvblox": nvblox_ready,
                "nvblox_healthy": nvblox_ready,
                "nvblox_warming_up": bool(
                    not nvblox_ready
                    and listed_topics is not None
                    and self._nvblox_node_present(listed_topics)
                ),
                "tf_chain": tf_diag.to_dict() if tf_diag else None,
                "ros_bridge_heartbeat": True,
                "obstacle_distance_m": self._optional_float_env("WAREHOUSE_OBSTACLE_DISTANCE_M"),
                "ceiling_distance_m": self._optional_float_env("WAREHOUSE_CEILING_DISTANCE_M"),
                "frontier_count": self._optional_float_env("WAREHOUSE_FRONTIER_COUNT"),
                "exploration_state": self._optional_str_env("WAREHOUSE_EXPLORATION_STATE"),
                "stereo_sync": stereo_sync,
                "tf_tree": tf_tree,
                "dock_marker": self._optional_bool_env("WAREHOUSE_DOCK_MARKER_VISIBLE"),
                "dock_marker_family": self._optional_str_env("WAREHOUSE_DOCK_MARKER_FAMILY"),
                "dock_marker_id": self._optional_str_env("WAREHOUSE_DOCK_MARKER_ID"),
                "dock_marker_size_m": self._optional_float_env("WAREHOUSE_DOCK_MARKER_SIZE_M"),
                "dock_marker_last_observed_at": self._optional_str_env(
                    "WAREHOUSE_DOCK_MARKER_LAST_OBSERVED_AT"
                ),
                "disk_free_bytes": disk.free,
                "disk_free_gb": round(disk.free / 1_000_000_000.0, 2),
                "gazebo": gazebo_status,
            },
        }

    @staticmethod
    def _format_health_detail(
        *,
        missing_required: list[str],
        missing_nvblox: list[str],
        nvblox_ready: bool,
        summary: dict[str, object],
        tf_detail: str,
        gazebo: dict[str, Any] | None = None,
    ) -> str | None:
        parts: list[str] = []
        if missing_required:
            parts.append(f"Missing required topics: {', '.join(missing_required)}")
        if missing_nvblox and not nvblox_ready:
            parts.append(f"Missing nvblox topics: {', '.join(missing_nvblox)}")
        if tf_detail and tf_detail != "ok":
            parts.append(f"TF chain: {tf_detail}")
        if isinstance(gazebo, dict) and not gazebo.get("sim_publishing"):
            parts.append(
                "Gazebo sensors not publishing (press Play in sim or start with gz sim -r ...)"
            )
        matches = summary.get("topic_matches")
        if isinstance(matches, dict):
            for key, payload in matches.items():
                if not isinstance(payload, dict):
                    continue
                if payload.get("healthy"):
                    continue
                expected = payload.get("expected")
                matched = payload.get("matched")
                error = payload.get("error")
                publishers = payload.get("publisher_count")
                publishing = payload.get("publishing")
                message_type = payload.get("message_type")
                verify_cmd = payload.get("verify_cmd")
                detail_bits = [
                    f"expected={expected}",
                    f"matched={matched or 'none'}",
                ]
                if publishers is not None:
                    detail_bits.append(f"publishers={publishers}")
                if publishing is not None:
                    detail_bits.append(f"messages={publishing}")
                if message_type:
                    detail_bits.append(f"type={message_type}")
                detail_bits.append(f"reason={error or 'unhealthy'}")
                if verify_cmd:
                    detail_bits.append(f"verify=`{verify_cmd}`")
                parts.append(f"{key}: " + " ".join(detail_bits))
        return "; ".join(parts) if parts else None

    @classmethod
    def _shallow_topic_diagnostic(cls, key: str, primary: str, listed_topics: set[str] | None):
        from .topic_diagnostics import TopicDiagnostic

        matched = cls._topic_key_present(key, primary, listed_topics)
        alias = None
        if matched:
            alias = primary if primary in (listed_topics or set()) else None
            if alias is None:
                for candidate in topic_registry().aliases.get(key, []):
                    if listed_topics and candidate in listed_topics:
                        alias = candidate
                        break
        return TopicDiagnostic(
            key=key,
            expected=primary,
            matched=alias if matched else None,
            listed=bool(matched),
            publisher_count=0,
            publishing=False,
            hz=None,
            last_message_age_s=None,
            message_type=None,
            healthy=False,
            error="shallow probe only — topic listed, publishers/messages not verified",
            readiness_state="shallow_pending" if matched else "topic_missing",
        )

    def _tf_from_deep_cache(self):
        from .topic_diagnostics import TfChainDiagnostic

        with self._health_lock:
            if self._deep_health_cache is None:
                return None
            _, payload = self._deep_health_cache
        tf_chain = payload.get("components", {}).get("tf_chain") if isinstance(payload, dict) else None
        if not isinstance(tf_chain, dict):
            return None
        return TfChainDiagnostic(
            odom_frame=str(tf_chain.get("odom_frame", "odom")),
            base_link_frame=str(tf_chain.get("base_link_frame", "base_link")),
            camera_frame=str(tf_chain.get("camera_frame", "front_rgbd_camera_link")),
            odom_to_base_link=bool(tf_chain.get("odom_to_base_link")),
            base_link_to_camera=bool(tf_chain.get("base_link_to_camera")),
            chain_ok=bool(tf_chain.get("chain_ok")),
            detail=str(tf_chain.get("detail") or "unknown"),
        )

    def _cached_tf_chain_probe(self):
        from .topic_diagnostics import TfChainDiagnostic, probe_tf_chain

        if not self._tf_probe_enabled():
            return None
        now = monotonic()
        if (
            self._last_tf_probe_result is not None
            and now - self._last_tf_probe_at <= self.TF_PROBE_INTERVAL_S
            and isinstance(self._last_tf_probe_result, TfChainDiagnostic)
        ):
            return self._last_tf_probe_result
        result = probe_tf_chain()
        self._last_tf_probe_at = now
        self._last_tf_probe_result = result
        return result

    def exploration_snapshot(self) -> dict[str, Any]:
        odometry_state = self._read_odometry_state()
        grid = self._optional_json_env("WAREHOUSE_EXPLORATION_GRID_JSON")
        if not isinstance(grid, dict):
            grid = self._default_exploration_grid()
        return {
            "pose": {
                "x_m": odometry_state.get("local_east_m", 0.0),
                "y_m": odometry_state.get("local_north_m", 0.0),
                "z_m": odometry_state.get("local_down_m", 0.0),
                "yaw_deg": odometry_state.get("yaw_deg"),
                "frame_id": "map",
            },
            "health": {
                "tracking_ok": bool(odometry_state.get("slam_tracking_ok", False)),
                "map_ready": True,
                "depth_healthy": self._optional_bool_env("WAREHOUSE_DEPTH_HEALTHY"),
                "localization_confidence": odometry_state.get("localization_confidence", 0.0),
                "odometry_drift_m": odometry_state.get("odometry_drift_m", 0.0),
                "loop_closure_quality": odometry_state.get("loop_closure_quality", 0.0),
            },
            "occupancy_grid": grid,
            "metadata": {
                "source": "nvblox_esdf",
                "frontier_count": self._optional_float_env("WAREHOUSE_FRONTIER_COUNT"),
            },
        }

    def _read_odometry_state(self) -> dict[str, Any]:
        path = self.config.odometry_state_path
        if not path.exists():
            logger.debug("Warehouse odometry state missing", extra={"path": str(path)})
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "Warehouse odometry state unreadable",
                extra={"path": str(path), "error": str(exc)},
            )
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _optional_bool_env(name: str) -> bool | None:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return None
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _optional_str_env(name: str) -> str | None:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return None
        return raw.strip()

    @staticmethod
    def _optional_float_env(name: str) -> float | None:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _optional_json_env(name: str) -> object | None:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _default_exploration_grid() -> dict[str, Any]:
        cells: list[dict[str, object]] = []
        for y_idx in range(15, 25):
            for x_idx in range(15, 25):
                cells.append({"x_idx": x_idx, "y_idx": y_idx, "state": "free"})
        return {
            "resolution_m": 0.5,
            "width": 40,
            "height": 40,
            "origin_x_m": -10.0,
            "origin_y_m": -10.0,
            "cells": cells,
        }

    @staticmethod
    def _topic_present(topic: str, listed_topics: set[str] | None) -> bool:
        if listed_topics is None or not topic:
            return False
        return topic in listed_topics

    @classmethod
    def _topic_key_present(
        cls,
        key: str,
        topic: str,
        listed_topics: set[str] | None,
    ) -> bool:
        if cls._topic_present(topic, listed_topics):
            return True
        for alias in topic_aliases().get(key, []):
            if cls._topic_present(alias, listed_topics):
                return True
        return False

    @staticmethod
    def _warehouse_topic_cache_usable(topics: set[str]) -> bool:
        if not topics:
            return False
        if any(name.startswith("/nvblox_node/") for name in topics):
            return True
        markers = (
            "/warehouse/",
            "/world/",
            "/scan",
            "/visual_slam/",
        )
        return any(any(name.startswith(prefix) for prefix in markers) for name in topics)

    @staticmethod
    def _sim_tf_broadcaster_active() -> bool:
        if not shutil.which("ros2"):
            return False
        ros_distro = os.getenv("ROS_DISTRO", "jazzy")
        ros_domain_id = os.getenv("ROS_DOMAIN_ID", "0")
        cmd = (
            f"source /opt/ros/{ros_distro}/setup.bash && "
            f"export ROS_DOMAIN_ID={ros_domain_id} && "
            "ros2 topic info /tf -v"
        )
        try:
            result = subprocess.run(
                ["bash", "-lc", cmd],
                check=False,
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return "warehouse_sim_tf_broadcaster" in f"{result.stdout}\n{result.stderr}"

    @staticmethod
    def _listed_nvblox_outputs(listed_topics: set[str] | None) -> bool:
        if not listed_topics:
            return False
        prefix = os.getenv("WAREHOUSE_NVBLOX_TOPIC_PREFIX", "/nvblox_node/")
        signals = ("mesh", "esdf", "occupancy", "pointcloud", "tsdf", "map_slice")
        return any(
            name.startswith(prefix) and any(signal in name for signal in signals)
            for name in listed_topics
        )

    @staticmethod
    def _nvblox_node_present(listed_topics: set[str] | None) -> bool:
        if not listed_topics:
            return False
        prefix = os.getenv("WAREHOUSE_NVBLOX_TOPIC_PREFIX", "/nvblox_node/")
        return any(name.startswith(prefix) for name in listed_topics)

    @staticmethod
    def _ros2_topic_list_cmd() -> str:
        ros_distro = os.getenv("ROS_DISTRO", "jazzy")
        ros_domain_id = os.getenv("ROS_DOMAIN_ID", "0")
        ros_ws_setup = os.getenv("ROS_WS_SETUP", "").strip()
        source_ws = f'source "{ros_ws_setup}" && ' if ros_ws_setup else ""
        return (
            f"source /opt/ros/{ros_distro}/setup.bash && "
            f"{source_ws}"
            f"export ROS_DOMAIN_ID={ros_domain_id} && "
            "ros2 topic list --no-daemon"
        )

    def _cached_tf_tree_probe(self, *, parent_frame: str, child_frame: str) -> bool | None:
        if not self._tf_probe_enabled():
            return None
        now = monotonic()
        if now - self._last_tf_probe_at <= self.TF_PROBE_INTERVAL_S:
            return self._last_tf_probe_result
        result = self._probe_tf_tree(parent_frame=parent_frame, child_frame=child_frame)
        self._last_tf_probe_at = now
        self._last_tf_probe_result = result
        return result

    @staticmethod
    def _tf_probe_enabled() -> bool:
        raw = os.getenv("WAREHOUSE_TF_PROBE_ON_HEALTH", "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @classmethod
    def _probe_tf_tree(cls, *, parent_frame: str, child_frame: str) -> bool | None:
        if not shutil.which("ros2"):
            return None
        ros_distro = os.getenv("ROS_DISTRO", "jazzy")
        ros_domain_id = os.getenv("ROS_DOMAIN_ID", "0")
        cmd = (
            f"source /opt/ros/{ros_distro}/setup.bash && "
            f"export ROS_DOMAIN_ID={ros_domain_id} && "
            f"timeout 1.0 ros2 run tf2_ros tf2_echo {shlex.quote(parent_frame)} "
            f"{shlex.quote(child_frame)}"
        )
        try:
            result = subprocess.run(
                ["bash", "-lc", cmd],
                check=False,
                capture_output=True,
                text=True,
                timeout=4.0,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        output = f"{result.stdout}\n{result.stderr}"
        if "At time" in output or "Translation:" in output:
            return True
        if "Invalid frame ID" in output or "Could not transform" in output:
            return False
        return None

    @staticmethod
    def _ros2_topics() -> set[str] | None:
        if not shutil.which("ros2"):
            logger.warning("ROS 2 CLI not found while probing warehouse topics")
            return None
        best: set[str] | None = None
        last_error: str | None = None
        for attempt in range(BridgeState.TOPIC_PROBE_ATTEMPTS):
            try:
                result = subprocess.run(
                    ["bash", "-lc", BridgeState._ros2_topic_list_cmd()],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10.0,
                )
            except subprocess.TimeoutExpired:
                last_error = "ros2 topic list timed out"
                if attempt + 1 < BridgeState.TOPIC_PROBE_ATTEMPTS:
                    time.sleep(0.75)
                continue
            except Exception as exc:
                last_error = f"ros2 topic list failed: {exc}"
                if attempt + 1 < BridgeState.TOPIC_PROBE_ATTEMPTS:
                    time.sleep(0.75)
                continue
            if result.returncode != 0:
                stderr = result.stderr.strip()[-500:]
                last_error = f"ros2 topic list returned {result.returncode}: {stderr}"
                if attempt + 1 < BridgeState.TOPIC_PROBE_ATTEMPTS:
                    time.sleep(0.75)
                continue
            topics = {line.strip() for line in result.stdout.splitlines() if line.strip()}
            if best is None or len(topics) > len(best):
                best = topics
            if len(topics) >= 8:
                return topics
            if attempt + 1 < BridgeState.TOPIC_PROBE_ATTEMPTS:
                time.sleep(0.75)
        if best is not None:
            return best
        if last_error:
            logger.warning("ROS 2 topic probe failed after retries: %s", last_error)
        return None

    def _stable_ros2_topics(self, *, fast: bool = False) -> set[str] | None:
        now = monotonic()
        if (
            self._last_nonempty_topics is not None
            and self._warehouse_topic_cache_usable(self._last_nonempty_topics)
            and (
                fast
                or now - self._last_nonempty_topics_at <= self.TOPIC_FAST_CACHE_S
            )
        ):
            return self._last_nonempty_topics
        listed_topics = self._ros2_topics()
        if listed_topics:
            self._last_nonempty_topics = listed_topics
            self._last_nonempty_topics_at = now
            self._last_probe_error = None
            return listed_topics
        if (
            self._last_nonempty_topics is not None
            and now - self._last_nonempty_topics_at <= self.TOPIC_CACHE_GRACE_S
            and self._warehouse_topic_cache_usable(self._last_nonempty_topics)
        ):
            logger.info(
                "Using cached warehouse ROS topics after empty probe count=%s age_s=%.2f",
                len(self._last_nonempty_topics),
                now - self._last_nonempty_topics_at,
                extra={
                    "cached_topic_count": len(self._last_nonempty_topics),
                    "cache_age_s": round(now - self._last_nonempty_topics_at, 2),
                },
            )
            return self._last_nonempty_topics
        if listed_topics == set():
            self._last_probe_error = "ros2 topic list returned no topics"
        elif listed_topics is None:
            self._last_probe_error = "ros2 topic list failed"
        return listed_topics

    def _log_health_change(
        self,
        *,
        ros_graph_ready: bool,
        ready: bool,
        topic_count: int | None,
        missing_required: list[str],
        missing_nvblox: list[str],
        probe_error: str | None,
        topic_matches: dict[str, object] | None = None,
    ) -> None:
        signature = (
            ros_graph_ready,
            ready,
            topic_count,
            tuple(missing_required),
            tuple(missing_nvblox),
            probe_error,
            tuple(sorted((topic_matches or {}).items())),
        )
        if signature == self._last_health_signature:
            return
        self._last_health_signature = signature
        log = logger.info if ready else logger.warning
        match_summary = {
            key: payload
            for key, payload in (topic_matches or {}).items()
            if isinstance(payload, dict) and not payload.get("healthy")
        }
        log(
            (
                "Warehouse ROS bridge health changed ready=%s ros_graph_ready=%s "
                "topic_count=%s missing_required=%s missing_nvblox=%s probe_error=%s "
                "unhealthy_topics=%s"
            ),
            ready,
            ros_graph_ready,
            topic_count,
            ",".join(missing_required) or "none",
            ",".join(missing_nvblox) or "none",
            probe_error or "none",
            json.dumps(match_summary, sort_keys=True) if match_summary else "none",
            extra={
                "ros_graph_ready": ros_graph_ready,
                "ready": ready,
                "topic_count": topic_count,
                "missing_required_topics": missing_required,
                "missing_nvblox_topics": missing_nvblox,
                "probe_error": probe_error,
                "topic_matches": topic_matches,
            },
        )

    def start_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        flight_id = safe_token(payload.get("flight_id"))
        warehouse_map_id = payload.get("warehouse_map_id")
        profile = str(payload.get("profile") or self.config.profile)
        session_dir = self.config.capture_root / f"flight_{flight_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Warehouse mapping start requested flight_id=%s map_id=%s profile=%s autolaunch=%s",
            flight_id,
            warehouse_map_id,
            profile,
            self.config.autolaunch,
            extra={
                "flight_id": flight_id,
                "warehouse_map_id": warehouse_map_id,
                "profile": profile,
                "session_dir": str(session_dir),
                "autolaunch": self.config.autolaunch,
            },
        )

        session = MappingSession(
            flight_id=flight_id,
            warehouse_map_id=int(warehouse_map_id) if warehouse_map_id is not None else None,
            profile=profile,
            session_dir=session_dir,
        )

        if self.config.autolaunch:
            process = self._launch_mapping_graph(session)
            session.launch_pid = process.pid
            self.processes[flight_id] = process
            logger.info(
                "Warehouse mapping launch process started flight_id=%s pid=%s",
                flight_id,
                process.pid,
                extra={"flight_id": flight_id, "pid": process.pid},
            )

        self.sessions[flight_id] = session
        mark_mapping_session_active(self.config.capture_root, flight_id)
        self._write_session_files(session, payload)
        return {
            "accepted": True,
            "status": "running",
            "detail": "Warehouse mapping session started",
            "data": {
                "flight_id": flight_id,
                "session_dir": str(session_dir),
                "launch_pid": session.launch_pid,
            },
        }

    def stop_mapping(self, flight_id: str) -> dict[str, Any]:
        safe_flight_id = safe_token(flight_id)
        session = self.sessions.get(safe_flight_id)
        if session is None:
            session_dir = self.config.capture_root / f"flight_{safe_flight_id}"
            session = MappingSession(
                flight_id=safe_flight_id,
                warehouse_map_id=None,
                profile=self.config.profile,
                session_dir=session_dir,
                status="stopped",
            )

        process = self.processes.pop(safe_flight_id, None)
        if process is not None:
            self._terminate_mapping_process(process)

        harvested = self._harvest_mapping_outputs(session)
        if harvested == 0:
            self._try_record_mapping_bag(session)
            time.sleep(2.0)
            self._harvest_mapping_outputs(session)

        session.status = "stopped"
        session.stopped_at = utc_now_iso()
        self._write_session_files(session, {})
        self._write_artifact_index(session)
        self.sessions.pop(safe_flight_id, None)
        if not self.sessions:
            clear_mapping_session_active(self.config.capture_root)
        logger.info(
            "Warehouse mapping session stopped flight_id=%s session_dir=%s",
            safe_flight_id,
            session.session_dir,
            extra={"flight_id": safe_flight_id, "session_dir": str(session.session_dir)},
        )
        return {
            "accepted": True,
            "status": "stopped",
            "detail": "Warehouse mapping session stopped",
            "data": {"flight_id": safe_flight_id, "session_dir": str(session.session_dir)},
        }

    def download_artifacts(self, flight_id: str, destination_dir: Path) -> dict[str, Any]:
        session_dir = self.config.capture_root / f"flight_{safe_token(flight_id)}"
        destination_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        if session_dir.exists():
            for src in session_dir.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(session_dir)
                dst = destination_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(str(dst))
        return {"accepted": True, "status": "downloaded", "paths": copied}

    def start_replay(self, payload: dict[str, Any]) -> dict[str, Any]:
        replay_id = safe_token(payload.get("replay_id"))
        replay_dir = self.config.capture_root / f"replay_{replay_id}"
        replay_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Warehouse replay start requested",
            extra={"replay_id": replay_id, "rosbag_path": payload.get("rosbag_path")},
        )
        write_json(
            replay_dir / "replay_manifest.json",
            {
                "replay_id": replay_id,
                "rosbag_path": payload.get("rosbag_path"),
                "profile": payload.get("profile") or self.config.profile,
                "started_at": utc_now_iso(),
            },
        )
        return {
            "accepted": True,
            "status": "running",
            "detail": "Replay session registered",
            "data": {"replay_id": replay_id, "session_dir": str(replay_dir)},
        }

    def stop_replay(self, replay_id: str) -> dict[str, Any]:
        safe_replay_id = safe_token(replay_id)
        replay_dir = self.config.capture_root / f"replay_{safe_replay_id}"
        write_json(
            replay_dir / "replay_stop.json",
            {"replay_id": safe_replay_id, "stopped_at": utc_now_iso()},
        )
        return {"accepted": True, "status": "stopped", "data": {"replay_id": safe_replay_id}}

    def _terminate_mapping_process(
        self,
        process: subprocess.Popen[bytes],
        *,
        timeout_s: float = 30.0,
    ) -> None:
        if process.poll() is not None:
            return
        logger.info(
            "Stopping warehouse mapping launch process pid=%s",
            process.pid,
            extra={"pid": process.pid},
        )
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = monotonic() + timeout_s
        while monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.5)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Warehouse mapping process did not exit after SIGKILL pid=%s", process.pid)

    def _harvest_mapping_outputs(self, session: MappingSession) -> int:
        artifacts_dir = session.session_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        search_roots: list[Path] = [
            session.session_dir / "isaac_outputs",
            session.session_dir / "artifacts",
        ]
        for env_name in ("WAREHOUSE_ISAAC_OUTPUT_DIR", "WAREHOUSE_NVBLOX_OUTPUT_DIR"):
            raw = os.getenv(env_name, "").strip()
            if raw:
                search_roots.append(Path(raw).expanduser())
        copied = 0
        seen: set[Path] = set()
        for root in search_roots:
            if not root.exists():
                continue
            for src in root.rglob("*"):
                if not src.is_file():
                    continue
                if src.suffix.lower() not in _ARTIFACT_EXTENSIONS and src.name != "tileset.json":
                    continue
                rel = src.name if root == artifacts_dir else src.relative_to(root)
                dst = artifacts_dir / rel
                if dst in seen or dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
                seen.add(dst)
        return copied

    def _try_record_mapping_bag(self, session: MappingSession) -> bool:
        listed_topics = self._stable_ros2_topics()
        if not listed_topics:
            return False
        topics = topic_env()
        record_topics: list[str] = []
        for key in ("pointcloud", "mesh", "depth", "raw_lidar", "visual_slam_odom", "local_odometry"):
            topic = (topics.get(key) or "").strip()
            if topic and topic in listed_topics and topic not in record_topics:
                record_topics.append(topic)
        if not record_topics:
            return False
        bag_path = session.session_dir / "artifacts" / "mapping_snapshot"
        if bag_path.exists():
            shutil.rmtree(bag_path, ignore_errors=True)
        cmd = ["ros2", "bag", "record", "-o", str(bag_path), "--duration", "5", *record_topics]
        try:
            result = subprocess.run(cmd, timeout=12, check=False, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            logger.warning(
                "Warehouse mapping rosbag snapshot failed flight_id=%s stderr=%s",
                session.flight_id,
                (result.stderr or "").strip(),
            )
            return False
        return bag_path.exists()

    def _launch_mapping_graph(self, session: MappingSession) -> subprocess.Popen[bytes]:
        env = os.environ.copy()
        env.update(
            {
                "WAREHOUSE_ACTIVE_FLIGHT_ID": session.flight_id,
                "WAREHOUSE_ACTIVE_SESSION_DIR": str(session.session_dir),
                "WAREHOUSE_ROS_PROFILE": session.profile,
            }
        )
        return subprocess.Popen(
            shlex.split(self.config.launch_cmd),
            env=env,
            start_new_session=True,
        )

    def _write_session_files(self, session: MappingSession, payload: dict[str, Any]) -> None:
        write_json(session.manifest_path, session.to_manifest())
        write_json(
            session.session_dir / "capture_metadata.json",
            {
                "flight_id": session.flight_id,
                "warehouse_map_id": session.warehouse_map_id,
                "profile": session.profile,
                "metadata": payload.get("metadata", {}),
                "calibration": payload.get("calibration", {}),
                "topics": topic_env(),
            },
        )
        write_json(
            session.session_dir / "mapping_health_summary.json",
            {
                "generated_at": utc_now_iso(),
                "profile": session.profile,
                "status": session.status,
                "topics": topic_env(),
            },
        )

    def _write_artifact_index(self, session: MappingSession) -> None:
        artifacts = []
        assets: dict[str, str] = {}
        for src in session.session_dir.rglob("*"):
            if not src.is_file():
                continue
            if src.name == "artifact_index.json":
                continue
            rel = str(src.relative_to(session.session_dir))
            suffix = src.suffix.lower()
            if src.name == "tileset.json":
                assets.setdefault("tileset", str(src.parent.relative_to(session.session_dir)))
            elif suffix in {".glb", ".gltf"}:
                assets.setdefault("mesh_glb", rel)
            elif suffix in {".pcd", ".ply", ".las", ".laz", ".e57"}:
                assets.setdefault("point_cloud", rel)
            elif suffix in {".db3", ".mcap", ".bag"}:
                assets.setdefault("rosbag", rel)
            elif suffix == ".tsdf":
                assets.setdefault("tsdf", rel)
            elif suffix == ".esdf":
                assets.setdefault("esdf", rel)
            elif src.name in {"mapping_quality_report.json", "quality_report.json"}:
                assets.setdefault("quality_report", rel)
            artifacts.append(
                {
                    "path": rel,
                    "size_bytes": src.stat().st_size,
                }
            )
        manifest = json.loads(session.manifest_path.read_text(encoding="utf-8"))
        manifest["assets"] = assets
        manifest["quality"] = self._quality_from_report(session.session_dir, assets)
        write_json(session.manifest_path, manifest)
        write_json(
            session.session_dir / "artifact_index.json",
            {"flight_id": session.flight_id, "generated_at": utc_now_iso(), "artifacts": artifacts},
        )

    @staticmethod
    def _quality_from_report(session_dir: Path, assets: dict[str, str]) -> dict[str, Any]:
        report_rel = assets.get("quality_report")
        if not report_rel:
            return {}
        report_path = session_dir / report_rel
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

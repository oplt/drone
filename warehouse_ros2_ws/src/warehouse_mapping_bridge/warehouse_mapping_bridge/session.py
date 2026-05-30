from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from pathlib import Path
from typing import Any

from .config import BridgeConfig, topic_env

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
    TOPIC_CACHE_GRACE_S = 10.0

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.config.capture_root.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, MappingSession] = {}
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self._last_nonempty_topics: set[str] | None = None
        self._last_nonempty_topics_at = 0.0
        self._last_probe_error: str | None = None
        self._last_health_signature: tuple[object, ...] | None = None

    def health(self) -> dict[str, Any]:
        topics = topic_env()
        listed_topics = self._stable_ros2_topics()
        disk = shutil.disk_usage(self.config.capture_root)
        odometry_state = self._read_odometry_state()
        topic_health = {
            key: self._topic_present(topic, listed_topics) for key, topic in topics.items()
        }
        rgb_camera_ready = topic_health["rgb_image"] or topic_health["rgb_image_compressed"]
        left_camera_ready = topic_health["left_image"] or topic_health["left_image_compressed"]
        right_camera_ready = topic_health["right_image"] or topic_health["right_image_compressed"]
        camera_ready = rgb_camera_ready or (left_camera_ready and right_camera_ready)
        vslam_ready = topic_health["visual_slam_odom"] or topic_health["local_odometry"]
        nvblox_ready = (
            topic_health["pointcloud"]
            or topic_health["mesh"]
            or topic_health["occupancy"]
            or topic_health["esdf"]
        )
        ros_graph_ready = listed_topics is not None
        missing_required = [
            key
            for key in (
                "rgb_image",
                "left_image",
                "right_image",
                "depth",
                "raw_lidar",
                "imu",
                "visual_slam_odom",
                "local_odometry",
            )
            if not topic_health.get(key)
        ]
        missing_nvblox = [
            key
            for key in (
                "pointcloud",
                "mesh",
                "mesh_marker",
                "occupancy",
                "esdf",
                "back_projected_depth",
            )
            if not topic_health.get(key)
        ]
        self._log_health_change(
            ros_graph_ready=ros_graph_ready,
            ready=bool(ros_graph_ready and camera_ready and topic_health["imu"] and vslam_ready),
            topic_count=len(listed_topics) if listed_topics is not None else None,
            missing_required=missing_required,
            missing_nvblox=missing_nvblox,
            probe_error=self._last_probe_error,
        )
        return {
            "status": "ready" if ros_graph_ready else "degraded",
            "ready": bool(ros_graph_ready and camera_ready and topic_health["imu"] and vslam_ready),
            "profile": self.config.profile,
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
                "topic_presence": topic_health,
                "camera_topics": camera_ready,
                "imu_topic": topic_health["imu"],
                "visual_slam": vslam_ready,
                "local_position_ok": bool(odometry_state.get("local_position_ok", False)),
                "slam_ready": bool(odometry_state.get("slam_ready", vslam_ready)),
                "slam_tracking_ok": bool(odometry_state.get("slam_tracking_ok", vslam_ready)),
                "localization_confidence": odometry_state.get("localization_confidence"),
                "odometry_drift_m": odometry_state.get("odometry_drift_m"),
                "local_odometry_state": odometry_state,
                "nvblox": nvblox_ready,
                "ros_bridge_heartbeat": True,
                "obstacle_distance_m": self._optional_float_env("WAREHOUSE_OBSTACLE_DISTANCE_M"),
                "ceiling_distance_m": self._optional_float_env("WAREHOUSE_CEILING_DISTANCE_M"),
                "frontier_count": self._optional_float_env("WAREHOUSE_FRONTIER_COUNT"),
                "exploration_state": self._optional_str_env("WAREHOUSE_EXPLORATION_STATE"),
                "stereo_sync": self._optional_bool_env("WAREHOUSE_STEREO_SYNC_OK"),
                "tf_tree": self._optional_bool_env("WAREHOUSE_TF_TREE_OK"),
                "dock_marker": self._optional_bool_env("WAREHOUSE_DOCK_MARKER_VISIBLE"),
                "dock_marker_family": self._optional_str_env("WAREHOUSE_DOCK_MARKER_FAMILY"),
                "dock_marker_id": self._optional_str_env("WAREHOUSE_DOCK_MARKER_ID"),
                "dock_marker_size_m": self._optional_float_env("WAREHOUSE_DOCK_MARKER_SIZE_M"),
                "dock_marker_last_observed_at": self._optional_str_env(
                    "WAREHOUSE_DOCK_MARKER_LAST_OBSERVED_AT"
                ),
                "disk_free_bytes": disk.free,
                "disk_free_gb": round(disk.free / 1_000_000_000.0, 2),
            },
        }

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
        if listed_topics is None:
            return False
        return topic in listed_topics

    @staticmethod
    def _ros2_topics() -> set[str] | None:
        if not shutil.which("ros2"):
            logger.warning("ROS 2 CLI not found while probing warehouse topics")
            return None
        try:
            result = subprocess.run(
                ["ros2", "topic", "list", "--no-daemon"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
        except subprocess.TimeoutExpired:
            logger.warning("ROS 2 topic probe timed out after %.1fs", 5.0)
            return None
        except Exception as exc:
            logger.warning("ROS 2 topic probe failed: %s", exc)
            return None
        if result.returncode != 0:
            stderr = result.stderr.strip()[-500:]
            logger.warning(
                "ROS 2 topic probe returned non-zero returncode=%s stderr=%s",
                result.returncode,
                stderr,
                extra={
                    "returncode": result.returncode,
                    "stderr": stderr,
                },
            )
            return None
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _stable_ros2_topics(self) -> set[str] | None:
        listed_topics = self._ros2_topics()
        now = monotonic()
        if listed_topics:
            self._last_nonempty_topics = listed_topics
            self._last_nonempty_topics_at = now
            self._last_probe_error = None
            return listed_topics
        if (
            listed_topics == set()
            and self._last_nonempty_topics is not None
            and now - self._last_nonempty_topics_at <= self.TOPIC_CACHE_GRACE_S
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
    ) -> None:
        signature = (
            ros_graph_ready,
            ready,
            topic_count,
            tuple(missing_required),
            tuple(missing_nvblox),
            probe_error,
        )
        if signature == self._last_health_signature:
            return
        self._last_health_signature = signature
        log = logger.info if ready else logger.warning
        log(
            (
                "Warehouse ROS bridge health changed ready=%s ros_graph_ready=%s "
                "topic_count=%s missing_required=%s missing_nvblox=%s probe_error=%s"
            ),
            ready,
            ros_graph_ready,
            topic_count,
            ",".join(missing_required) or "none",
            ",".join(missing_nvblox) or "none",
            probe_error or "none",
            extra={
                "ros_graph_ready": ros_graph_ready,
                "ready": ready,
                "topic_count": topic_count,
                "missing_required_topics": missing_required,
                "missing_nvblox_topics": missing_nvblox,
                "probe_error": probe_error,
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

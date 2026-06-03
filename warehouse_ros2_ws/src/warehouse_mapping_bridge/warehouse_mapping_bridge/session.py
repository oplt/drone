from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path
from time import monotonic
from typing import Any

from .config import BridgeConfig, topic_aliases, topic_env, topic_registry
from .process_supervisor import exited_during_grace, start_process, terminate_process
from .session_model import (
    MappingSession,
    clear_mapping_session_active,
    mapping_session_active_path,
    mark_mapping_session_active,
    safe_token,
    utc_now_iso,
    write_json,
)
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
    ".bin",
}


class BridgeState:
    TOPIC_CACHE_GRACE_S = 90.0
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
        self.replay_processes: dict[str, subprocess.Popen[bytes]] = {}
        self.export_jobs: dict[str, threading.Thread] = {}
        self.export_status: dict[str, dict[str, Any]] = {}
        self._session_lock = threading.RLock()
        self._last_nonempty_topics: set[str] | None = None
        self._last_nonempty_topics_at = 0.0
        self._last_probe_error: str | None = None
        self._last_health_signature: tuple[object, ...] | None = None
        self._health_cache: tuple[float, dict[str, Any]] | None = None
        self._deep_health_cache: tuple[float, dict[str, Any]] | None = None
        self._shallow_health_cache: tuple[float, dict[str, Any]] | None = None
        self._health_lock = threading.Lock()
        self._deep_probe_lock = threading.Lock()
        self._deep_probe_in_progress = False
        self._deep_probe_started_at: float | None = None
        self._topic_env = topic_env()
        self._topic_profile = topic_registry().profile
        self._last_tf_probe_at = 0.0
        self._last_tf_probe_result: object | None = None
        self._bridge_started_at = monotonic()
        if self._background_probe_enabled():
            threading.Thread(
                target=self._deep_health_refresh_loop,
                daemon=True,
                name="warehouse-health-probe",
            ).start()
        self._recover_export_status()
        self._recover_active_session()

    @staticmethod
    def _background_probe_enabled() -> bool:
        raw = os.getenv("WAREHOUSE_HEALTH_BACKGROUND_PROBE", "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _deep_probe_enabled() -> bool:
        raw = os.getenv("WAREHOUSE_HEALTH_DEEP_PROBE", "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _recover_active_session(self) -> None:
        active_path = mapping_session_active_path(self.config.capture_root)
        if not active_path.exists():
            return
        try:
            flight_id = safe_token(active_path.read_text(encoding="utf-8").strip())
        except OSError:
            return
        if not flight_id or flight_id == "unknown":
            return
        session_dir = self.config.capture_root / f"flight_{flight_id}"
        manifest_path = session_dir / "warehouse_mapping_manifest.json"
        warehouse_map_id: int | None = None
        profile = self.config.profile
        started_at = utc_now_iso()
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    profile = str(manifest.get("profile") or profile)
                    started_at = str(manifest.get("started_at") or started_at)
                    raw_map_id = manifest.get("warehouse_map_id")
                    warehouse_map_id = int(raw_map_id) if raw_map_id is not None else None
            except Exception:
                logger.warning(
                    "Failed to recover warehouse mapping manifest",
                    extra={"path": str(manifest_path)},
                )
        self.sessions[flight_id] = MappingSession(
            flight_id=flight_id,
            warehouse_map_id=warehouse_map_id,
            profile=profile,
            session_dir=session_dir,
            started_at=started_at,
            status="recovered",
        )

    def _recover_export_status(self) -> None:
        for status_path in self.config.capture_root.glob("flight_*/export_status.json"):
            flight_id = safe_token(status_path.parent.name.removeprefix("flight_"))
            try:
                payload = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            status = str(payload.get("status") or "unknown")
            if status == "running":
                payload = {
                    **payload,
                    "status": "interrupted",
                    "finished_at": utc_now_iso(),
                    "error": "bridge restarted during export finalization",
                }
                write_json(status_path, payload)
            self.export_status[flight_id] = payload

    @classmethod
    def _topic_list_probe_config(cls, *, background: bool) -> tuple[float, int]:
        if background:
            timeout_s = float(os.getenv("WAREHOUSE_ROS_TOPIC_LIST_BG_TIMEOUT_S", "2.0"))
            attempts = int(os.getenv("WAREHOUSE_ROS_TOPIC_LIST_BG_ATTEMPTS", "1"))
        else:
            timeout_s = float(os.getenv("WAREHOUSE_ROS_TOPIC_LIST_TIMEOUT_S", "2.0"))
            attempts = int(os.getenv("WAREHOUSE_ROS_TOPIC_LIST_ATTEMPTS", "1"))
        return max(0.5, timeout_s), max(1, attempts)

    def _set_deep_probe_state(self, running: bool) -> None:
        with self._health_lock:
            self._deep_probe_in_progress = running
            self._deep_probe_started_at = monotonic() if running else None

    def _deep_probe_age_s(self) -> float | None:
        with self._health_lock:
            if self._deep_probe_started_at is None:
                return None
            return round(monotonic() - self._deep_probe_started_at, 2)

    @classmethod
    def _health_sample_max_age_s(cls) -> float:
        """Wall-clock age allowed for health_sample_timestamp before preflight warns."""
        override = os.getenv("WAREHOUSE_HEALTH_SAMPLE_MAX_AGE_S", "").strip()
        if override:
            try:
                return max(5.0, float(override))
            except ValueError:
                pass
        if cls._background_probe_enabled():
            refresh_s = float(os.getenv("WAREHOUSE_HEALTH_REFRESH_INTERVAL_S", "15.0"))
            probe_budget_s = float(os.getenv("WAREHOUSE_HEALTH_DEEP_PROBE_BUDGET_S", "45.0"))
            return max(cls.DEEP_HEALTH_STALE_S, refresh_s * 2.0 + probe_budget_s)
        return cls.DEEP_HEALTH_STALE_S

    def _cache_deep_payload(self, payload: dict[str, Any]) -> None:
        components = payload.get("components")
        if isinstance(components, dict):
            probe_error = components.get("ros_topic_probe_error")
            topic_count = int(components.get("ros_topic_count") or 0)
            if probe_error and topic_count == 0:
                logger.warning(
                    "Warehouse health probe incomplete (topic_count=0): %s",
                    probe_error,
                )
                payload["diagnostics_ready"] = False
                payload["cache_ready"] = False

        now = monotonic()
        with self._health_lock:
            self._deep_health_cache = (now, payload)
            self._shallow_health_cache = (now, self._shallow_from_deep(payload))

    def _deep_health_refresh_loop(self) -> None:
        startup_delay_s = float(os.getenv("WAREHOUSE_HEALTH_STARTUP_DELAY_S", "1.0"))
        if startup_delay_s > 0:
            time.sleep(startup_delay_s)

        interval_s = float(
            os.getenv("WAREHOUSE_HEALTH_REFRESH_INTERVAL_S", "15.0")
        )

        while True:
            if not self._deep_probe_lock.acquire(blocking=False):
                logger.debug("Warehouse deep health refresh skipped; probe already running")
                time.sleep(max(1.0, interval_s))
                continue

            started = monotonic()
            self._set_deep_probe_state(True)

            try:
                timeout_s, attempts = self._topic_list_probe_config(background=True)
                payload = self._build_health(
                    deep=True,
                    topic_list_timeout_s=timeout_s,
                    topic_list_attempts=attempts,
                )
                payload = dict(payload)
                payload["probe_mode"] = "deep_background"
                payload["from_cache"] = False
                payload["probe_in_progress"] = False
                payload["probe_duration_ms"] = round((monotonic() - started) * 1000, 2)
                payload["cache_ready"] = True
                payload["diagnostics_ready"] = True

                self._cache_deep_payload(payload)

                logger.info(
                    "Warehouse deep health refresh complete duration_ms=%s "
                    "status=%s ready=%s topic_count=%s",
                    payload["probe_duration_ms"],
                    payload.get("status"),
                    payload.get("ready"),
                    payload.get("components", {}).get("ros_topic_count"),
                )
            except Exception:
                logger.exception("Warehouse deep health refresh failed")
            finally:
                self._set_deep_probe_state(False)
                self._deep_probe_lock.release()

            time.sleep(max(1.0, interval_s))

    def health(self, *, deep: bool = False, force: bool = False) -> dict[str, Any]:
        if not deep:
            return self._health_from_cache(deep=False, force=force)

        if force:
            return self._run_deep_health_probe(probe_mode="deep_forced")

        if self._background_probe_enabled():
            return self._health_from_cache(deep=True, force=False)

        stale_s = float(os.getenv("WAREHOUSE_HEALTH_DEEP_STALE_S", str(self.DEEP_HEALTH_STALE_S)))

        with self._health_lock:
            probe_in_progress = self._deep_probe_in_progress
            deep_cache = self._deep_health_cache
            shallow_cache = self._shallow_health_cache

            if probe_in_progress and deep_cache is not None:
                return self._decorate_cached_health(
                    deep_cache,
                    probe_mode="deep_cached",
                    probe_in_progress=True,
                )

            if probe_in_progress:
                if shallow_cache is not None:
                    return self._decorate_cached_health(
                        shallow_cache,
                        probe_mode="shallow_cached",
                        probe_in_progress=True,
                    )
                return self._empty_health_payload(probe_in_progress=True)

            if deep_cache is not None:
                cached_at, _cached_payload = deep_cache
                age_s = monotonic() - cached_at
                if age_s <= stale_s:
                    return self._decorate_cached_health(
                        deep_cache,
                        probe_mode="deep_cached",
                        probe_in_progress=False,
                    )

        return self._run_deep_health_probe(probe_mode="deep")

    def _run_deep_health_probe(self, *, probe_mode: str) -> dict[str, Any]:
        if not self._deep_probe_lock.acquire(blocking=False):
            with self._health_lock:
                deep_cache = self._deep_health_cache
                shallow_cache = self._shallow_health_cache
                if deep_cache is not None:
                    return self._decorate_cached_health(
                        deep_cache,
                        probe_mode="deep_cached",
                        probe_in_progress=True,
                    )
                if shallow_cache is not None:
                    return self._decorate_cached_health(
                        shallow_cache,
                        probe_mode="shallow_cached",
                        probe_in_progress=True,
                    )
            return self._empty_health_payload(probe_in_progress=True)

        started = monotonic()
        self._set_deep_probe_state(True)

        try:
            timeout_s, attempts = self._topic_list_probe_config(background=False)
            payload = self._build_health(
                deep=True,
                topic_list_timeout_s=timeout_s,
                topic_list_attempts=attempts,
            )
            payload = dict(payload)
            payload["probe_mode"] = probe_mode
            payload["from_cache"] = False
            payload["probe_in_progress"] = False
            payload["probe_duration_ms"] = round((monotonic() - started) * 1000, 2)
            payload.setdefault("diagnostics_ready", True)
            payload.setdefault("cache_ready", True)
            self._cache_deep_payload(payload)
            return payload
        finally:
            self._set_deep_probe_state(False)
            self._deep_probe_lock.release()

    def _health_from_cache(self, *, deep: bool, force: bool = False) -> dict[str, Any]:
        del deep
        refresh_candidate: tuple[float, dict[str, Any]] | None = None
        force_refresh_candidate: dict[str, Any] | None = None

        with self._health_lock:
            probe_in_progress = self._deep_probe_in_progress
            shallow_cache = self._shallow_health_cache
            deep_cache = self._deep_health_cache

            if shallow_cache is not None and not force:
                cached_at, cached_payload = shallow_cache
                age_s = monotonic() - cached_at
                refresh_s = float(os.getenv("WAREHOUSE_HEALTH_SHALLOW_REFRESH_S", "8.0"))
                if age_s > refresh_s and not probe_in_progress:
                    refresh_candidate = (cached_at, dict(cached_payload))
                else:
                    return self._decorate_cached_health(
                        shallow_cache,
                        probe_mode="shallow_cached",
                        probe_in_progress=probe_in_progress,
                    )

            elif deep_cache is not None:
                cached_at, deep_payload = deep_cache
                out = self._shallow_from_deep(deep_payload)
                if force and not probe_in_progress:
                    force_refresh_candidate = out
                else:
                    out["probe_in_progress"] = probe_in_progress
                    out["probe_age_s"] = round(monotonic() - cached_at, 2)
                    out["cache_ready"] = True
                    out["diagnostics_ready"] = True
                    return out

        if refresh_candidate is not None:
            refreshed = self._refresh_shallow_payload(refresh_candidate[1])
            if refreshed is not None:
                with self._health_lock:
                    self._shallow_health_cache = (monotonic(), dict(refreshed))
                return refreshed

            return self._decorate_cached_health(
                refresh_candidate,
                probe_mode="shallow_cached",
                probe_in_progress=False,
            )

        if force_refresh_candidate is not None:
            refreshed = self._refresh_shallow_payload(force_refresh_candidate)
            if refreshed is not None:
                with self._health_lock:
                    self._shallow_health_cache = (monotonic(), dict(refreshed))
                return refreshed

            force_refresh_candidate["probe_in_progress"] = False
            force_refresh_candidate["cache_ready"] = True
            force_refresh_candidate["diagnostics_ready"] = True
            return force_refresh_candidate

        return self._empty_health_payload(probe_in_progress=probe_in_progress)

    def _refresh_shallow_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Reconcile cached health with a fast ROS topic list (fixes stale missing topics)."""
        timeout_s, attempts = self._topic_list_probe_config(background=True)
        listed_topics = self._stable_ros2_topics(
            fast=True,
            timeout_s=timeout_s,
            attempts=attempts,
        )
        if not self._warehouse_topic_cache_usable(listed_topics):
            return None

        from .topic_diagnostics import summarize_diagnostics

        topics = topic_env()
        registry = topic_registry()
        probe_keys = sorted(set(registry.required_for_perception))
        diagnostics = {
            key: self._shallow_topic_diagnostic(key, topics.get(key, ""), listed_topics)
            for key in probe_keys
            if topics.get(key)
        }
        summary = summarize_diagnostics(diagnostics)
        from .topic_diagnostics import _coerce_topic_diagnostic

        coerced = {
            key: _coerce_topic_diagnostic(key, diag) for key, diag in diagnostics.items()
        }
        topic_health = {key: diag.healthy for key, diag in coerced.items()}
        camera_ready = topic_health.get("rgb_image", False) or (
            topic_health.get("left_image", False) and topic_health.get("right_image", False)
        )
        vslam_ready = topic_health.get("visual_slam_odom", False)
        local_odom_ready = topic_health.get("local_odometry", False)

        missing_required = [
            key
            for key in summary["missing_required_topics"]
            if key not in {"rgb_image", "left_image", "right_image"}
        ]
        if not camera_ready:
            missing_required.append("rgb_image")

        odometry_state, odometry_state_unreadable = self._read_odometry_state()
        odom_fresh, odom_age_s, slam_tracking_ok = self._odometry_tracking_state(
            odometry_state,
            deep_probe=False,
            vslam_topic_ready=vslam_ready,
        )
        if odometry_state_unreadable:
            odom_fresh = False
            slam_tracking_ok = False

        out = dict(payload)
        components = dict(out.get("components") or {})
        components["listed_topics"] = sorted(listed_topics)
        components["ros_topic_count"] = len(listed_topics)
        components["topic_diagnostics"] = {k: d.to_dict() for k, d in coerced.items()}
        components["missing_required_topics"] = missing_required
        components["camera_topics"] = camera_ready
        components["imu_healthy"] = topic_health.get("imu", False)
        components["raw_lidar_healthy"] = topic_health.get("raw_lidar", False)
        components["visual_slam"] = vslam_ready
        components["visual_slam_healthy"] = vslam_ready
        components["local_odometry_healthy"] = local_odom_ready
        components["slam_tracking_ok"] = slam_tracking_ok
        components["odometry_fresh"] = odom_fresh
        components["odometry_age_s"] = odom_age_s
        components["odometry_state_unreadable"] = odometry_state_unreadable
        components["local_odometry_state"] = odometry_state
        components["odometry_topic"] = topics.get("visual_slam_odom") or topics.get(
            "local_odometry"
        )
        components["odometry_source"] = (
            "sim_odom" if registry.profile == "gazebo" else "vslam_odom"
        )
        left_ok = topic_health.get("left_image", False)
        right_ok = topic_health.get("right_image", False)
        components["stereo_sync"] = (
            True
            if left_ok and right_ok
            else True
            if camera_ready and not (left_ok or right_ok)
            else None
        )
        components["tf_tree"] = payload.get("components", {}).get("tf_tree", True)
        require_raw_lidar = topic_registry().profile != "gazebo" or os.getenv(
            "WAREHOUSE_REQUIRE_RAW_LIDAR", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        capabilities = self._build_capabilities(
            bridge_alive=True,
            ros_graph_ready=bool(listed_topics),
            topic_health=topic_health,
            nvblox_ready=any(
                topic_health.get(key, False)
                for key in topic_registry().required_for_nvblox_any
            ),
            odom_fresh=odom_fresh or vslam_ready,
            require_lidar=require_raw_lidar,
            tf_tree=bool(components.get("tf_tree", True)),
        )
        components["capabilities"] = capabilities
        core_ready = bool(capabilities.get("can_fly_warehouse_scan"))
        health_status = self._resolve_health_status(
            can_fly=core_ready,
            ros_graph_ready=bool(listed_topics),
            sensors_listed=bool(listed_topics and any("/warehouse/" in t for t in listed_topics)),
        )
        out["components"] = components
        out["ready"] = core_ready
        out["core_ready"] = core_ready
        out["mapping_ready"] = bool(capabilities.get("can_map_3d"))
        out["status"] = health_status
        out["capabilities"] = capabilities
        out["probe_mode"] = "shallow_refreshed"
        out["from_cache"] = True
        sample_ts = time.time()
        out["health_sample_timestamp"] = sample_ts
        components["health_sample_timestamp"] = sample_ts
        components["health_sample_max_age_ms"] = int(self._health_sample_max_age_s() * 1000)
        out["components"] = components
        return out

    @staticmethod
    def _decorate_cached_health(
            cache_entry: tuple[float, dict[str, Any]],
            *,
            probe_mode: str,
            probe_in_progress: bool,
    ) -> dict[str, Any]:
        cached_at, cached_payload = cache_entry
        out = dict(cached_payload)
        out["probe_mode"] = probe_mode
        out["from_cache"] = True
        out["probe_in_progress"] = probe_in_progress
        out["probe_age_s"] = round(monotonic() - cached_at, 2)
        out["cache_ready"] = True
        out["diagnostics_ready"] = True
        return out

    def _shallow_from_deep(self, deep_payload: dict[str, Any]) -> dict[str, Any]:
        shallow = dict(deep_payload)
        shallow["probe_mode"] = "shallow_cached"
        shallow["from_cache"] = True
        shallow["probe_in_progress"] = False
        shallow["cache_ready"] = bool(deep_payload.get("cache_ready", True))
        shallow["diagnostics_ready"] = bool(deep_payload.get("diagnostics_ready", True))
        return shallow

    def _empty_health_payload(self, *, probe_in_progress: bool) -> dict[str, Any]:
        if probe_in_progress:
            with self._health_lock:
                if self._deep_health_cache is not None:
                    cached_at, cached_payload = self._deep_health_cache
                    return self._decorate_cached_health(
                        (cached_at, dict(cached_payload)),
                        probe_mode=str(cached_payload.get("probe_mode") or "deep_cached"),
                        probe_in_progress=True,
                    )
                if self._shallow_health_cache is not None:
                    cached_at, cached_payload = self._shallow_health_cache
                    return self._decorate_cached_health(
                        (cached_at, dict(cached_payload)),
                        probe_mode=str(cached_payload.get("probe_mode") or "shallow_cached"),
                        probe_in_progress=True,
                    )

        disk = shutil.disk_usage(self.config.capture_root)
        probe_age_s = self._deep_probe_age_s() if probe_in_progress else None

        return {
            "status": self._resolve_health_status(
                can_fly=False,
                ros_graph_ready=False,
                sensors_listed=False,
            ),
            "ready": False,
            "detail": (
                "Health diagnostics warming; /health is alive but ROS diagnostics "
                "cache is not ready yet"
            ),
            "profile": self.config.profile,
            "topic_profile": self._topic_profile,
            "bridge_flow": os.getenv("WAREHOUSE_BRIDGE_FLOW", self._topic_profile),
            "capture_root": str(self.config.capture_root),
            "websocket_url": self.config.ros_ws_url,
            "probe_mode": "cache_empty",
            "from_cache": False,
            "probe_in_progress": probe_in_progress,
            "probe_in_progress_age_s": probe_age_s,
            "cache_ready": False,
            "diagnostics_ready": False,
            "components": {
                "ros2_cli": bool(shutil.which("ros2")),
                "ros_graph": False,
                "autolaunch": self.config.autolaunch,
                "active_sessions": len(self.sessions),
                "topics": self._topic_env,
                "listed_topics": [],
                "ros_topic_count": 0,
                "ros_topic_probe_error": "diagnostics cache is warming",
                "missing_required_topics": list(topic_registry().required_for_perception),
                "missing_nvblox_topics": [],
                "topic_presence": {},
                "topic_diagnostics": {},
                "topic_matches": {},
                "ros_bridge_heartbeat": True,
                "diagnostics_pending": True,
                "disk_free_bytes": disk.free,
                "disk_free_gb": round(disk.free / 1_000_000_000.0, 2),
            },
        }

    @staticmethod
    def _nvblox_process_running() -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "[n]vblox_ros.*nvblox_node"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False
        return result.returncode == 0

    @staticmethod
    def _nvblox_health_checks_enabled(listed_topics: set[str] | None) -> bool:
        """Only probe nvblox outputs when the mapping stack is actually running."""
        raw = os.getenv("WAREHOUSE_BRIDGE_HEALTH_CHECK_NVBLOX", "auto").strip().lower()
        if raw in {"0", "false", "no", "off", "never"}:
            return False
        if raw in {"1", "true", "yes", "on", "always"}:
            return True
        if BridgeState._nvblox_node_present(listed_topics):
            return True
        return BridgeState._nvblox_process_running()

    def _build_health(
        self,
        *,
        deep: bool,
        topic_list_timeout_s: float | None = None,
        topic_list_attempts: int | None = None,
    ) -> dict[str, Any]:
        registry = topic_registry()
        topics = topic_env()
        if topic_list_timeout_s is None or topic_list_attempts is None:
            default_timeout, default_attempts = self._topic_list_probe_config(background=False)
            topic_list_timeout_s = (
                topic_list_timeout_s if topic_list_timeout_s is not None else default_timeout
            )
            topic_list_attempts = (
                topic_list_attempts if topic_list_attempts is not None else default_attempts
            )
        listed_topics = self._stable_ros2_topics(
            fast=not deep,
            timeout_s=topic_list_timeout_s,
            attempts=topic_list_attempts,
        )
        check_nvblox = self._nvblox_health_checks_enabled(listed_topics)
        disk = shutil.disk_usage(self.config.capture_root)
        odometry_state, odometry_state_unreadable = self._read_odometry_state()

        probe_keys = sorted(set(registry.required_for_perception) | {"left_image", "right_image"})
        if check_nvblox:
            probe_keys = sorted(set(probe_keys) | set(registry.required_for_nvblox_any))
        deep_probe = deep or self._deep_probe_enabled()
        if deep_probe:
            diagnostics = probe_topics(listed_topics, keys=probe_keys)
        else:
            diagnostics = {
                key: self._shallow_topic_diagnostic(key, topics.get(key, ""), listed_topics)
                for key in probe_keys
                if topics.get(key)
            }

        summary = summarize_diagnostics(diagnostics, include_nvblox=check_nvblox)
        topic_health = {key: diag.healthy for key, diag in diagnostics.items()}
        topic_presence = {
            key: diag.listed or diag.publishing or diag.healthy
            for key, diag in diagnostics.items()
        }

        rgb_ok = topic_health.get("rgb_image", False)
        left_ok = topic_health.get("left_image", False)
        right_ok = topic_health.get("right_image", False)
        camera_ready = rgb_ok or (left_ok and right_ok)

        vslam_diag = diagnostics.get("visual_slam_odom")
        local_odom_diag = diagnostics.get("local_odometry")
        imu_diag = diagnostics.get("imu")
        vslam_ready = bool(vslam_diag and vslam_diag.healthy)
        local_odom_ready = bool(local_odom_diag and local_odom_diag.healthy)
        odom_fresh, odom_age_s, slam_tracking_ok = self._odometry_tracking_state(
            odometry_state,
            deep_probe=deep_probe,
            vslam_topic_ready=vslam_ready,
        )
        if odometry_state_unreadable:
            odom_fresh = False
            slam_tracking_ok = False

        if check_nvblox:
            nvblox_ready = any(
                topic_health.get(key, False)
                for key in registry.required_for_nvblox_any
            )
            if (
                not nvblox_ready
                and listed_topics is not None
                and self._nvblox_node_present(listed_topics)
                and any(topic.startswith("/nvblox_node/") for topic in listed_topics)
            ):
                # Truncated ros2 topic list may omit contract map topics while nvblox runs.
                nvblox_ready = True
            missing_nvblox = list(summary["missing_nvblox_topics"])
            nvblox_process_running = self._nvblox_process_running()
            if not nvblox_ready and nvblox_process_running:
                nvblox_ready = True
                nvblox_warming = True
            else:
                nvblox_warming = bool(
                    not nvblox_ready
                    and (
                        nvblox_process_running
                        or (
                            listed_topics is not None
                            and self._nvblox_node_present(listed_topics)
                        )
                    )
                )
        else:
            nvblox_ready = False
            missing_nvblox = []
            nvblox_warming = False

        ros_graph_ready = listed_topics is not None and len(listed_topics) > 0

        missing_required = [
            key
            for key in summary["missing_required_topics"]
            if key not in {"rgb_image", "left_image", "right_image"}
        ]
        if not camera_ready:
            missing_required.append("rgb_image")
        if listed_topics is not None and len(listed_topics) == 0:
            missing_required = list(dict.fromkeys(registry.required_for_perception))

        gazebo_status = None
        gazebo_probe_disabled = os.getenv(
            "WAREHOUSE_GAZEBO_PROBE_ON_HEALTH", "1"
        ).strip().lower() in {"0", "false", "no", "off"}

        if registry.profile == "gazebo" and deep and not gazebo_probe_disabled:
            gazebo_status = probe_gazebo_sensors()

        tf_probe_enabled = self._tf_probe_enabled()

        if deep and tf_probe_enabled:
            tf_diag = self._cached_tf_chain_probe()
        elif not deep:
            tf_diag = self._tf_from_deep_cache()
        else:
            tf_diag = None

        override_tf = self._optional_bool_env("WAREHOUSE_TF_TREE_OK")
        if override_tf is not None:
            tf_tree = override_tf
        elif tf_diag is not None:
            tf_tree = tf_diag.chain_ok
        else:
            # TF diagnostics are unknown/disabled. Do not block fast health readiness.
            # Use WAREHOUSE_TF_PROBE_ON_HEALTH=1 when you want strict TF validation.
            tf_tree = True

        stereo_sync = self._optional_bool_env("WAREHOUSE_STEREO_SYNC_OK")
        if stereo_sync is None and left_ok and right_ok:
            stereo_sync = True

        require_raw_lidar = registry.profile != "gazebo" or os.getenv(
            "WAREHOUSE_REQUIRE_RAW_LIDAR", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        capabilities = self._build_capabilities(
            bridge_alive=True,
            ros_graph_ready=ros_graph_ready,
            topic_health=topic_health,
            nvblox_ready=nvblox_ready,
            odom_fresh=odom_fresh or vslam_ready,
            require_lidar=require_raw_lidar,
            tf_tree=tf_tree,
        )
        core_ready = bool(capabilities.get("can_fly_warehouse_scan"))
        perception_ready = core_ready
        health_status = self._resolve_health_status(
            can_fly=core_ready,
            ros_graph_ready=ros_graph_ready,
            sensors_listed=bool(
                listed_topics is not None
                and any("/warehouse/" in topic for topic in listed_topics)
            ),
        )

        health_detail = self._format_health_detail(
            missing_required=missing_required,
            missing_nvblox=missing_nvblox,
            nvblox_ready=nvblox_ready,
            summary=summary,
            tf_detail=(
                tf_diag.detail
                if tf_diag
                else None
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
        mapping_ready = bool(nvblox_ready)
        sample_ts = time.time()
        health_layers = self._build_health_layers(
            bridge_alive=True,
            ros_graph_ready=ros_graph_ready,
            capabilities=capabilities,
            nvblox_warming=nvblox_warming,
            nvblox_deferred=not check_nvblox,
            can_fly=core_ready,
            nvblox_ready=nvblox_ready,
        )
        components_payload = {
                "bridge_flow": os.getenv("WAREHOUSE_BRIDGE_FLOW", registry.profile),
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
                "depth_health": bool(
                    diagnostics.get("depth") and diagnostics["depth"].healthy
                ),
                "raw_lidar_healthy": bool(
                    diagnostics.get("raw_lidar") and diagnostics["raw_lidar"].healthy
                ),
                "visual_slam": vslam_ready,
                "vslam": vslam_ready,
                "visual_slam_tracking": vslam_ready,
                "visual_slam_healthy": vslam_ready,
                "local_odometry_healthy": local_odom_ready,
                "local_position_ok": bool(odometry_state.get("local_position_ok", False)),
                "slam_ready": slam_tracking_ok if slam_tracking_ok is not None else vslam_ready,
                "slam_tracking_ok": slam_tracking_ok,
                "odometry_fresh": odom_fresh,
                "odometry_age_s": odom_age_s,
                "odometry_state_unreadable": odometry_state_unreadable,
                "odometry_topic": topics.get("visual_slam_odom") or topics.get("local_odometry"),
                "odometry_source": (
                    "sim_odom" if registry.profile == "gazebo" else "vslam_odom"
                ),
                "localization_confidence": odometry_state.get("localization_confidence"),
                "odometry_drift_m": odometry_state.get("odometry_drift_m"),
                "local_odometry_state": odometry_state,
                "nvblox": nvblox_ready,
                "nvblox_healthy": nvblox_ready and not nvblox_warming,
                "nvblox_warming_up": nvblox_warming,
                "nvblox_process_running": self._nvblox_process_running(),
                "nvblox_checks_active": check_nvblox,
                "nvblox_deferred": not check_nvblox,
                "tf_chain": tf_diag.to_dict() if tf_diag else None,
                "tf_available": bool(tf_diag.chain_ok) if tf_diag else tf_tree,
                "required_tf_edges": (
                    [list(edge) for edge in tf_diag.required_tf_edges] if tf_diag else []
                ),
                "missing_tf_edges": (
                    [list(edge) for edge in tf_diag.missing_tf_edges] if tf_diag else []
                ),
                "ros_bridge_heartbeat": True,
                "obstacle_distance_m": self._optional_float_env("WAREHOUSE_OBSTACLE_DISTANCE_M"),
                "ceiling_distance_m": self._optional_float_env("WAREHOUSE_CEILING_DISTANCE_M"),
                "frontier_count": self._optional_float_env("WAREHOUSE_FRONTIER_COUNT"),
                "exploration_state": self._optional_str_env("WAREHOUSE_EXPLORATION_STATE"),
                "stereo_sync": stereo_sync,
                "tf_tree": tf_tree,
                "odometry_frame_id": odometry_state.get("frame_id"),
                "odometry_child_frame_id": odometry_state.get("child_frame_id"),
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
                "capabilities": capabilities,
                "health_layers": health_layers,
                "health_sample_timestamp": sample_ts,
                "health_sample_max_age_ms": int(self._health_sample_max_age_s() * 1000),
                "health_cache_ttl_ms": int(self.HEALTH_CACHE_TTL_S * 1000),
            }
        return {
            "status": health_status,
            "ready": core_ready,
            "core_ready": core_ready,
            "mapping_ready": mapping_ready,
            "bridge_alive": True,
            "capabilities": capabilities,
            "health_layers": health_layers,
            "health_sample_timestamp": sample_ts,
            "detail": health_detail,
            "profile": self.config.profile,
            "topic_profile": registry.profile,
            "bridge_flow": os.getenv("WAREHOUSE_BRIDGE_FLOW", registry.profile),
            "capture_root": str(self.config.capture_root),
            "websocket_url": self.config.ros_ws_url,
            "components": components_payload,
        }

    @staticmethod
    def _health_startup_grace_s() -> float:
        raw = os.getenv("WAREHOUSE_HEALTH_STARTUP_GRACE_S", "60")
        try:
            return max(5.0, float(raw))
        except ValueError:
            return 60.0

    def _resolve_health_status(
        self,
        *,
        can_fly: bool,
        ros_graph_ready: bool,
        sensors_listed: bool,
    ) -> str:
        elapsed = monotonic() - self._bridge_started_at
        grace_s = self._health_startup_grace_s()
        if elapsed < 3.0:
            return "starting"
        if can_fly:
            return "ready"
        if elapsed < grace_s:
            if not ros_graph_ready or not sensors_listed:
                return "waiting_for_gazebo"
            return "bridging"
        return "degraded"

    @staticmethod
    def _build_health_layers(
        *,
        bridge_alive: bool,
        ros_graph_ready: bool,
        capabilities: dict[str, bool],
        nvblox_warming: bool,
        nvblox_deferred: bool = False,
        can_fly: bool,
        nvblox_ready: bool,
    ) -> dict[str, str]:
        def layer(ok: bool, *, missing: str = "missing", degraded: str = "degraded") -> str:
            return "ok" if ok else degraded if degraded else missing

        if nvblox_deferred:
            nvblox_layer = "deferred"
        elif nvblox_ready:
            nvblox_layer = "ok"
        elif nvblox_warming:
            nvblox_layer = "warming"
        else:
            nvblox_layer = "missing"

        return {
            "bridge_liveness": "ok" if bridge_alive else "down",
            "ros_graph": "ok" if ros_graph_ready else "missing",
            "sensor_inputs": (
                "ok"
                if capabilities.get("can_perceive_rgb")
                and capabilities.get("can_perceive_depth")
                and capabilities.get("can_perceive_imu")
                else "degraded"
            ),
            "slam": "ok" if capabilities.get("can_localize") else "missing",
            "nvblox": nvblox_layer,
            "artifact_export": "not_ready",
            "can_fly_warehouse_scan": "ok" if can_fly else "degraded",
            "can_map_3d": "ok" if capabilities.get("can_map_3d") else "degraded",
            "overall_mapping_ready": "ok" if can_fly else "degraded",
        }

    @staticmethod
    def _build_capabilities(
        *,
        bridge_alive: bool,
        ros_graph_ready: bool,
        topic_health: dict[str, bool],
        nvblox_ready: bool,
        odom_fresh: bool,
        require_lidar: bool,
        tf_tree: bool = True,
    ) -> dict[str, bool]:
        can_localize = bool(
            odom_fresh
            or topic_health.get("visual_slam_odom")
            or topic_health.get("local_odometry")
        )
        can_perceive_depth = bool(topic_health.get("depth"))
        can_perceive_rgb = bool(topic_health.get("rgb_image"))
        can_scan_lidar = bool(topic_health.get("raw_lidar")) or not require_lidar
        can_perceive_imu = bool(topic_health.get("imu"))
        can_map_3d = bool(nvblox_ready and tf_tree)
        can_fly = bool(
            bridge_alive
            and ros_graph_ready
            and can_localize
            and can_perceive_depth
            and can_perceive_rgb
            and can_scan_lidar
            and can_perceive_imu
        )
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
            "tf_available": bool(tf_tree),
            "can_fly_warehouse_scan": can_fly,
            "can_build_warehouse_map": can_map_3d,
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
        rgb_ok = False
        if isinstance(matches, dict):
            rgb_payload = matches.get("rgb_image")
            if isinstance(rgb_payload, dict) and rgb_payload.get("healthy"):
                rgb_ok = True
        optional_when_rgbd = {"left_image", "right_image"}
        if isinstance(matches, dict):
            for key, payload in matches.items():
                if not isinstance(payload, dict):
                    continue
                if payload.get("healthy"):
                    continue
                if rgb_ok and key in optional_when_rgbd:
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
        from .topic_diagnostics import (
            TopicDiagnostic,
            _fast_resolve_topic_from_graph,
            _gazebo_sensor_stream_live,
        )

        matched = cls._topic_key_present(key, primary, listed_topics)
        alias = None
        if matched:
            alias = primary if primary in (listed_topics or set()) else None
            if alias is None:
                for candidate in topic_registry().aliases.get(key, []):
                    if listed_topics and candidate in listed_topics:
                        alias = candidate
                        break
            if alias is None and listed_topics is not None:
                alias = _fast_resolve_topic_from_graph(key, primary, listed_topics)
        elif topic_registry().profile == "gazebo" and _gazebo_sensor_stream_live(key):
            # Gazebo streams can be live on gz topics before contract relays appear in ros2 topic list.
            matched = True
            alias = primary
        return TopicDiagnostic(
            key=key,
            expected=primary,
            matched=alias if matched else None,
            listed=bool(matched),
            publisher_count=1 if matched else 0,
            publishing=bool(matched),
            hz=None,
            last_message_age_s=None,
            message_type=None,
            healthy=bool(matched),
            error=None if matched else "topic not listed in graph",
            readiness_state="shallow_present" if matched else "topic_missing",
        )

    def _tf_from_deep_cache(self):
        from .topic_diagnostics import TfChainDiagnostic

        max_age_s = max(
            5.0,
            float(os.getenv("WAREHOUSE_TF_DEEP_CACHE_MAX_AGE_S", "25.0")),
        )
        with self._health_lock:
            if self._deep_health_cache is None:
                return None
            cached_at, payload = self._deep_health_cache
            if monotonic() - cached_at > max_age_s:
                return None
        tf_chain = (
            payload.get("components", {}).get("tf_chain")
            if isinstance(payload, dict)
            else None
        )
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
            required_tf_edges=tuple(
                tuple(str(part) for part in edge)
                for edge in tf_chain.get("required_tf_edges", [])
                if isinstance(edge, list | tuple) and len(edge) == 2
            ),
            missing_tf_edges=tuple(
                tuple(str(part) for part in edge)
                for edge in tf_chain.get("missing_tf_edges", [])
                if isinstance(edge, list | tuple) and len(edge) == 2
            ),
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
        odometry_state, _unreadable = self._read_odometry_state()
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

    def _read_odometry_state(self) -> tuple[dict[str, Any], bool]:
        path = self.config.odometry_state_path
        if not path.exists():
            logger.debug("Warehouse odometry state missing", extra={"path": str(path)})
            return {}, False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            topic = topic_env().get("visual_slam_odom") or topic_env().get(
                "local_odometry", "/warehouse/drone/odometry"
            )
            logger.warning(
                "Warehouse local odometry state unreadable; block autonomous flight until "
                "%s is publishing again",
                topic,
                extra={"path": str(path), "topic": topic, "error": str(exc)},
            )
            return {}, True
        if not isinstance(payload, dict):
            return {}, True
        return payload, False

    @classmethod
    def _odometry_tracking_state(
        cls,
        odometry_state: dict[str, Any],
        *,
        deep_probe: bool,
        vslam_topic_ready: bool,
    ) -> tuple[bool, float | None, bool | None]:
        """Return (odometry_fresh, age_s, slam_tracking_ok)."""
        import time as _time

        max_age_s = float(os.getenv("WAREHOUSE_ODOMETRY_MAX_AGE_S", "2.0"))
        age_s: float | None = None
        fresh = False

        updated_mono = odometry_state.get("updated_at_monotonic")
        if isinstance(updated_mono, (int, float)):
            age_s = max(0.0, _time.monotonic() - float(updated_mono))
            fresh = age_s <= max_age_s
        else:
            stamp = odometry_state.get("timestamp_utc")
            if isinstance(stamp, str) and stamp.strip():
                try:
                    from datetime import datetime

                    normalized = stamp.replace("Z", "+00:00")
                    stamp_ts = datetime.fromisoformat(normalized).timestamp()
                    age_s = max(0.0, _time.time() - stamp_ts)
                    fresh = age_s <= max_age_s
                except ValueError:
                    fresh = False

        explicit_tracking = odometry_state.get("slam_tracking_ok")
        localization_mode = os.getenv("WAREHOUSE_LOCALIZATION_MODE", "").strip().lower()
        gazebo_gt = localization_mode in {
            "",
            "gazebo_ground_truth",
            "gazebo_gt",
            "gazebo",
            "sim",
        } and (
            os.getenv("WAREHOUSE_TOPIC_PROFILE", "").strip().lower() == "gazebo"
            or os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower()
            in {"1", "true", "yes", "on"}
            or os.getenv("WAREHOUSE_BRIDGE_FLOW", "").strip().lower() == "gazebo"
        )
        if fresh:
            if gazebo_gt:
                return fresh, age_s, True
            if explicit_tracking is False and not vslam_topic_ready:
                return fresh, age_s, False
            return fresh, age_s, True

        if deep_probe:
            if not odometry_state:
                return False, None, False if not vslam_topic_ready else None
            return False, age_s, False

        return False, age_s, None

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
        source_ws = (
            f'if [ -f "{ros_ws_setup}" ]; then source "{ros_ws_setup}"; fi && '
            if ros_ws_setup
            else ""
        )
        return (
            'REPO_ROOT="$(pwd)" && '
            'PATH="${PATH//$REPO_ROOT\\/.venv\\/bin:/}" && '
            'PATH="${PATH//:$REPO_ROOT\\/.venv\\/bin/}" && '
            'PATH="${PATH//$REPO_ROOT\\/.venv\\/bin/}" && '
            'PATH="${PATH//$REPO_ROOT\\/backend\\/.venv\\/bin:/}" && '
            'PATH="${PATH//:$REPO_ROOT\\/backend\\/.venv\\/bin/}" && '
            'PATH="${PATH//$REPO_ROOT\\/backend\\/.venv\\/bin/}" && '
            "unset VIRTUAL_ENV PYTHONHOME && "
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
        raw = os.getenv("WAREHOUSE_TF_PROBE_ON_HEALTH", "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @classmethod
    def _probe_tf_tree(cls, *, parent_frame: str, child_frame: str) -> bool | None:
        if not shutil.which("ros2"):
            return None
        ros_distro = os.getenv("ROS_DISTRO", "jazzy")
        ros_domain_id = os.getenv("ROS_DOMAIN_ID", "0")
        cmd = (
            'REPO_ROOT="$(pwd)" && '
            'PATH="${PATH//$REPO_ROOT\\/.venv\\/bin:/}" && '
            'PATH="${PATH//:$REPO_ROOT\\/.venv\\/bin/}" && '
            'PATH="${PATH//$REPO_ROOT\\/.venv\\/bin/}" && '
            'PATH="${PATH//$REPO_ROOT\\/backend\\/.venv\\/bin:/}" && '
            'PATH="${PATH//:$REPO_ROOT\\/backend\\/.venv\\/bin/}" && '
            'PATH="${PATH//$REPO_ROOT\\/backend\\/.venv\\/bin/}" && '
            "unset VIRTUAL_ENV PYTHONHOME && "
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
    def _ros2_topics(*, timeout_s: float = 2.5, attempts: int = 1) -> set[str] | None:
        graph_backend = os.getenv("WAREHOUSE_GRAPH_PROBE_BACKEND", "auto").strip().lower()
        if graph_backend in {
            "rclpy",
            "auto",
        }:
            from .ros_graph import rclpy_topic_names

            graph_topics = rclpy_topic_names(timeout_s=min(timeout_s, 1.0))
            min_topics = int(os.getenv("WAREHOUSE_GRAPH_PROBE_MIN_TOPICS", "8"))
            if graph_topics and len(graph_topics) >= min_topics:
                return graph_topics
            if graph_backend == "rclpy":
                return graph_topics

        if not shutil.which("ros2"):
            logger.warning("ROS 2 CLI not found while probing warehouse topics")
            return None
        best: set[str] | None = None
        last_error: str | None = None
        for attempt in range(max(1, attempts)):
            try:
                result = subprocess.run(
                    ["bash", "-lc", BridgeState._ros2_topic_list_cmd()],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired:
                last_error = "ros2 topic list timed out"
                if attempt + 1 < attempts:
                    time.sleep(0.25)
                continue
            except Exception as exc:
                last_error = f"ros2 topic list failed: {exc}"
                if attempt + 1 < attempts:
                    time.sleep(0.25)
                continue
            if result.returncode != 0:
                stderr = result.stderr.strip()[-500:]
                last_error = f"ros2 topic list returned {result.returncode}: {stderr}"
                if attempt + 1 < attempts:
                    time.sleep(0.25)
                continue
            topics = {line.strip() for line in result.stdout.splitlines() if line.strip()}
            if best is None or len(topics) > len(best):
                best = topics
            if len(topics) >= 8:
                return topics
            if attempt + 1 < attempts:
                time.sleep(0.25)
        if best is not None:
            return best
        if last_error:
            logger.warning("ROS 2 topic probe failed after retries: %s", last_error)
        return None

    def _stable_ros2_topics(
        self,
        *,
        fast: bool = False,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> set[str] | None:
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
        if timeout_s is None or attempts is None:
            timeout_s, attempts = self._topic_list_probe_config(background=False)
        listed_topics = self._ros2_topics(timeout_s=timeout_s, attempts=attempts)
        if listed_topics:
            self._last_nonempty_topics = listed_topics
            self._last_nonempty_topics_at = now
            self._last_probe_error = None
            return listed_topics
        cache_grace_s = float(
            os.getenv("WAREHOUSE_TOPIC_CACHE_GRACE_S", str(self.TOPIC_CACHE_GRACE_S))
        )
        if (
            self._last_nonempty_topics is not None
            and now - self._last_nonempty_topics_at <= cache_grace_s
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
        raw_flight_id = str(payload.get("flight_id") or "").strip()
        if not raw_flight_id:
            return {
                "accepted": False,
                "status": "rejected",
                "detail": "flight_id is required",
                "data": {},
            }

        flight_id = safe_token(raw_flight_id)
        warehouse_map_id = payload.get("warehouse_map_id")
        profile = str(payload.get("profile") or self.config.profile)
        bridge_flow = str(payload.get("bridge_flow") or os.getenv("WAREHOUSE_BRIDGE_FLOW", profile))
        session_dir = self.config.capture_root / f"flight_{flight_id}"

        with self._session_lock:
            existing = self.sessions.get(flight_id)
            if existing is not None:
                return {
                    "accepted": True,
                    "status": existing.status,
                    "detail": "Warehouse mapping session is already running for this flight_id",
                    "data": {
                        "flight_id": flight_id,
                        "session_dir": str(existing.session_dir),
                        "launch_pid": existing.launch_pid,
                    },
                }

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
                "bridge_flow": bridge_flow,
                    "session_dir": str(session_dir),
                    "autolaunch": self.config.autolaunch,
                },
            )

            session = MappingSession(
                flight_id=flight_id,
                warehouse_map_id=int(warehouse_map_id) if warehouse_map_id is not None else None,
                profile=profile,
                session_dir=session_dir,
                status="starting" if self.config.autolaunch else "running",
            )
            self.sessions[flight_id] = session
            self._write_session_files(session, payload)

        if self.config.autolaunch:
            try:
                process = self._launch_mapping_graph(session)
            except Exception as exc:
                with self._session_lock:
                    session.status = "failed"
                    self._write_session_files(session, payload)
                return {
                    "accepted": False,
                    "status": "failed",
                    "detail": f"Warehouse mapping launch failed: {exc}",
                    "data": {
                        "flight_id": flight_id,
                        "session_dir": str(session_dir),
                    },
                }
            launch_grace_s = float(os.getenv("WAREHOUSE_LAUNCH_STARTUP_GRACE_S", "1.0"))
            launch_failed = exited_during_grace(process, grace_s=launch_grace_s)
            with self._session_lock:
                session.launch_pid = process.pid
                if launch_failed:
                    session.status = "failed"
                    self._write_session_files(session, payload)
                    return {
                        "accepted": False,
                        "status": "failed",
                        "detail": (
                            "Warehouse mapping launch exited immediately with "
                            f"rc={process.returncode}"
                        ),
                        "data": {
                            "flight_id": flight_id,
                            "session_dir": str(session_dir),
                            "launch_pid": session.launch_pid,
                            "returncode": process.returncode,
                        },
                    }
                self.processes[flight_id] = process
                session.status = "running"
                mark_mapping_session_active(self.config.capture_root, flight_id)
                self._write_session_files(session, payload)
                logger.info(
                    "Warehouse mapping launch process started flight_id=%s pid=%s",
                    flight_id,
                    process.pid,
                    extra={"flight_id": flight_id, "pid": process.pid},
                )
        else:
            with self._session_lock:
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

    def mapping_status(self, flight_id: str | None = None) -> dict[str, Any]:
        with self._session_lock:
            sessions = dict(self.sessions)
            processes = dict(self.processes)
            export_status = {key: dict(value) for key, value in self.export_status.items()}

        if flight_id:
            safe_flight_id = safe_token(flight_id)
            session = sessions.get(safe_flight_id)
            session_dir = self.config.capture_root / f"flight_{safe_flight_id}"
            manifest_path = session_dir / "warehouse_mapping_manifest.json"
            manifest: dict[str, Any] = {}
            if session is None and manifest_path.exists():
                try:
                    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = payload if isinstance(payload, dict) else {}
                except Exception:
                    manifest = {}
            process = processes.get(safe_flight_id)
            data = session.to_manifest() if session else manifest
            if not data:
                return {
                    "accepted": False,
                    "status": "not_found",
                    "data": {"flight_id": safe_flight_id},
                }
            persisted_export_status: dict[str, Any] = {}
            export_status_path = session_dir / "export_status.json"
            if export_status_path.exists():
                try:
                    persisted = json.loads(export_status_path.read_text(encoding="utf-8"))
                    if isinstance(persisted, dict):
                        persisted_export_status = persisted
                except Exception:
                    persisted_export_status = {}
            data["process_alive"] = bool(process and process.poll() is None)
            data["export"] = export_status.get(safe_flight_id, persisted_export_status)
            return {"accepted": True, "status": data.get("status", "unknown"), "data": data}

        out: list[dict[str, Any]] = []
        for key, session in sessions.items():
            process = processes.get(key)
            payload = session.to_manifest()
            payload["process_alive"] = bool(process and process.poll() is None)
            payload["export"] = export_status.get(key, {})
            out.append(payload)
        return {
            "accepted": True,
            "status": "ok",
            "data": {
                "sessions": out,
                "active_count": len(out),
                "export_jobs": sorted(self.export_jobs.keys()),
            },
        }

    def stop_mapping(self, flight_id: str) -> dict[str, Any]:
        safe_flight_id = safe_token(flight_id)

        with self._session_lock:
            session = self.sessions.pop(safe_flight_id, None)
            process = self.processes.pop(safe_flight_id, None)

        if session is None:
            session_dir = self.config.capture_root / f"flight_{safe_flight_id}"
            session = MappingSession(
                flight_id=safe_flight_id,
                warehouse_map_id=None,
                profile=self.config.profile,
                session_dir=session_dir,
                status="stopped",
            )

        if process is not None:
            self._terminate_mapping_process(process)

        session.status = "finalizing"
        session.stopped_at = utc_now_iso()
        self._write_session_files(session, {})

        with self._session_lock:
            if self.sessions:
                next_flight_id = next(iter(self.sessions.keys()))
                mark_mapping_session_active(self.config.capture_root, next_flight_id)
            else:
                clear_mapping_session_active(self.config.capture_root)

        export_thread = threading.Thread(
            target=self._finalize_mapping_outputs,
            args=(session,),
            daemon=False,
            name=f"warehouse-export-{safe_flight_id}",
        )
        self.export_jobs[safe_flight_id] = export_thread
        self.export_status[safe_flight_id] = {
            "status": "running",
            "started_at": utc_now_iso(),
            "finished_at": None,
            "harvested_artifacts": 0,
            "error": None,
        }
        self._write_export_status(session)
        export_thread.start()

        logger.info(
            "Warehouse mapping session stop accepted flight_id=%s session_dir=%s",
            safe_flight_id,
            session.session_dir,
            extra={
                "flight_id": safe_flight_id,
                "session_dir": str(session.session_dir),
            },
        )
        return {
            "accepted": True,
            "status": "finalizing",
            "detail": (
                "Warehouse mapping session stopped; artifact export is finalizing "
                "in background"
            ),
            "data": {"flight_id": safe_flight_id, "session_dir": str(session.session_dir)},
        }

    def _finalize_mapping_outputs(self, session: MappingSession) -> None:
        harvested = 0
        try:
            listed_topics = self._stable_ros2_topics()
            from .nvblox_export import export_nvblox_artifacts

            export_nvblox_artifacts(
                session.session_dir,
                listed_topics=listed_topics,
                profile=session.profile,
            )
            harvested = self._harvest_mapping_outputs(session)
            if harvested == 0 and self._try_record_mapping_bag(session):
                harvested = self._harvest_mapping_outputs(session)
            session.status = "stopped"
            session.stopped_at = session.stopped_at or utc_now_iso()
            self._write_session_files(session, {})
            self._write_artifact_index(session)
            self.export_status[session.flight_id] = {
                **self.export_status.get(session.flight_id, {}),
                "status": "complete",
                "finished_at": utc_now_iso(),
                "harvested_artifacts": harvested,
                "error": None,
            }
            self._write_export_status(session)
            logger.info(
                "Warehouse mapping artifact finalization complete flight_id=%s harvested=%s",
                session.flight_id,
                harvested,
                extra={"flight_id": session.flight_id, "harvested_artifacts": harvested},
            )
        except Exception:
            session.status = "export_failed"
            self.export_status[session.flight_id] = {
                **self.export_status.get(session.flight_id, {}),
                "status": "failed",
                "finished_at": utc_now_iso(),
                "error": "artifact finalization failed",
            }
            self._write_session_files(session, {})
            self._write_export_status(session)
            logger.exception(
                "Warehouse mapping artifact finalization failed flight_id=%s",
                session.flight_id,
            )
        finally:
            self.export_jobs.pop(session.flight_id, None)

    def _write_export_status(self, session: MappingSession) -> None:
        status = self.export_status.get(session.flight_id)
        if not status:
            return
        write_json(session.session_dir / "export_status.json", dict(status))

    def download_artifacts(self, flight_id: str, destination_dir: Path) -> dict[str, Any]:
        session_dir = self.config.capture_root / f"flight_{safe_token(flight_id)}"
        if not session_dir.exists():
            return {
                "accepted": False,
                "status": "not_found",
                "detail": "No warehouse mapping session artifacts found for this flight_id",
                "paths": [],
            }

        session_root = session_dir.resolve()
        destination_root = destination_dir.expanduser().resolve()
        if destination_root == session_root or destination_root.is_relative_to(session_root):
            return {
                "accepted": False,
                "status": "rejected",
                "detail": "destination_dir must not be inside the source session directory",
                "paths": [],
            }

        destination_root.mkdir(parents=True, exist_ok=True)
        sources = [src for src in session_dir.rglob("*") if src.is_file()]
        copied: list[str] = []
        for src in sources:
            rel = src.relative_to(session_dir)
            dst = destination_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(str(dst))
        return {"accepted": True, "status": "downloaded", "paths": copied}

    def start_replay(self, payload: dict[str, Any]) -> dict[str, Any]:
        replay_id = safe_token(payload.get("replay_id"))
        replay_dir = self.config.capture_root / f"replay_{replay_id}"
        replay_dir.mkdir(parents=True, exist_ok=True)
        rosbag_path = Path(str(payload.get("rosbag_path") or "")).expanduser()
        if not rosbag_path.exists():
            return {
                "accepted": False,
                "status": "not_found",
                "detail": "rosbag_path does not exist",
                "data": {"replay_id": replay_id, "rosbag_path": str(rosbag_path)},
            }
        if replay_id in self.replay_processes and self.replay_processes[replay_id].poll() is None:
            return {
                "accepted": True,
                "status": "running",
                "detail": "Replay session is already running",
                "data": {"replay_id": replay_id, "session_dir": str(replay_dir)},
            }
        logger.info(
            "Warehouse replay start requested",
            extra={"replay_id": replay_id, "rosbag_path": str(rosbag_path)},
        )
        env = os.environ.copy()
        env["WAREHOUSE_ROS_PROFILE"] = str(payload.get("profile") or self.config.profile)
        cmd = ["ros2", "bag", "play", str(rosbag_path), "--clock"]
        process = start_process(cmd, env=env, log_path=replay_dir / "replay.log")
        self.replay_processes[replay_id] = process
        write_json(
            replay_dir / "replay_manifest.json",
            {
                "replay_id": replay_id,
                "rosbag_path": str(rosbag_path),
                "profile": payload.get("profile") or self.config.profile,
                "started_at": utc_now_iso(),
                "launch_pid": process.pid,
            },
            )
        return {
            "accepted": True,
            "status": "running",
            "detail": "Replay session started",
            "data": {
                "replay_id": replay_id,
                "session_dir": str(replay_dir),
                "launch_pid": process.pid,
            },
        }

    def stop_replay(self, replay_id: str) -> dict[str, Any]:
        safe_replay_id = safe_token(replay_id)
        replay_dir = self.config.capture_root / f"replay_{safe_replay_id}"
        process = self.replay_processes.pop(safe_replay_id, None)
        if process is not None:
            self._terminate_mapping_process(process)
        write_json(
            replay_dir / "replay_stop.json",
            {"replay_id": safe_replay_id, "stopped_at": utc_now_iso()},
            )
        return {"accepted": True, "status": "stopped", "data": {"replay_id": safe_replay_id}}

    def _terminate_mapping_process(
            self,
            process: subprocess.Popen[bytes],
            *,
            timeout_s: float = 8.0,
    ) -> None:
        if process.poll() is not None:
            return
        logger.info(
            "Stopping warehouse mapping launch process pid=%s",
            process.pid,
            extra={"pid": process.pid},
        )
        try:
            terminate_process(process, timeout_s=timeout_s)
        except Exception:
            logger.warning("Warehouse mapping process termination failed pid=%s", process.pid)

    def _harvest_mapping_outputs(self, session: MappingSession) -> int:
        artifacts_dir = session.session_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        def is_artifact(path: Path) -> bool:
            return path.suffix.lower() in _ARTIFACT_EXTENSIONS or path.name == "tileset.json"

        existing = sum(1 for src in artifacts_dir.rglob("*") if src.is_file() and is_artifact(src))
        search_roots: list[Path] = [session.session_dir / "isaac_outputs"]
        for env_name in ("WAREHOUSE_ISAAC_OUTPUT_DIR", "WAREHOUSE_NVBLOX_OUTPUT_DIR"):
            raw = os.getenv(env_name, "").strip()
            if raw:
                search_roots.append(Path(raw).expanduser())

        copied = 0
        seen: set[Path] = set()
        artifacts_root = artifacts_dir.resolve()
        for root in search_roots:
            if not root.exists():
                continue
            root_resolved = root.resolve()
            if root_resolved == artifacts_root or root_resolved.is_relative_to(artifacts_root):
                continue
            for src in root.rglob("*"):
                if not src.is_file() or not is_artifact(src):
                    continue
                src_resolved = src.resolve()
                if src_resolved == artifacts_root or src_resolved.is_relative_to(artifacts_root):
                    continue
                dst = artifacts_dir / src.relative_to(root)
                if dst in seen or dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
                seen.add(dst)
        return existing + copied

    def _try_record_mapping_bag(self, session: MappingSession) -> bool:
        from .nvblox_export import record_mapping_snapshot, record_snapshot_on_stop_enabled

        if not record_snapshot_on_stop_enabled(profile=session.profile):
            return False

        listed_topics = self._stable_ros2_topics()
        return record_mapping_snapshot(session.session_dir, listed_topics=listed_topics) > 0

    def _launch_mapping_graph(self, session: MappingSession) -> subprocess.Popen[bytes]:
        env = os.environ.copy()
        env.update(
            {
                "WAREHOUSE_ACTIVE_FLIGHT_ID": session.flight_id,
                "WAREHOUSE_ACTIVE_SESSION_DIR": str(session.session_dir),
                "WAREHOUSE_ROS_PROFILE": session.profile,
                "WAREHOUSE_BRIDGE_FLOW": os.getenv("WAREHOUSE_BRIDGE_FLOW", session.profile),
            }
        )
        return start_process(
            self.config.launch_cmd,
            env=env,
            log_path=session.session_dir / "launch.log",
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
            elif suffix == ".ply":
                assets.setdefault("mesh", rel)
            elif suffix in {".pcd", ".las", ".laz", ".e57"}:
                assets.setdefault("point_cloud", rel)
            elif suffix in {".bin", ".map"}:
                assets.setdefault("nvblox_map", rel)
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

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.modules.warehouse.service.safety import (
    WarehouseSafetyDecision,
    evaluate_warehouse_runtime_safety,
)


def _gazebo_sim_enabled() -> bool:
    return os.getenv("WAREHOUSE_GAZEBO_SIM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def default_odometry_max_age_s() -> float:
    """Hard limit for local pose freshness during takeoff and in-flight safety."""
    return _float_env("WAREHOUSE_ODOMETRY_MAX_AGE_S", 2.0)


def _default_odometry_stale_s() -> float:
    return _float_env("WAREHOUSE_RUNTIME_ODOMETRY_STALE_S", default_odometry_max_age_s())


@dataclass(frozen=True)
class OdometryStateRead:
    payload: dict[str, Any] | None = None
    unreadable: bool = False
    missing: bool = False


def read_odometry_state_file() -> OdometryStateRead:
    raw_path = os.getenv(
        "WAREHOUSE_ODOMETRY_STATE_PATH",
        "backend/storage/warehouse_ros/latest_odometry.json",
    )
    path = Path(raw_path).expanduser()
    if not path.is_file():
        return OdometryStateRead(missing=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OdometryStateRead(unreadable=True)
    if not isinstance(payload, dict):
        return OdometryStateRead(unreadable=True)
    return OdometryStateRead(payload=payload)


def odometry_topic_path(components: dict[str, Any]) -> str:
    topics_raw = components.get("topics")
    topics = topics_raw if isinstance(topics_raw, dict) else {}
    for key in ("visual_slam_odom", "local_odometry"):
        topic = topics.get(key)
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    topic_diag_raw = components.get("topic_diagnostics")
    topic_diag = topic_diag_raw if isinstance(topic_diag_raw, dict) else {}
    for key in ("visual_slam_odom", "local_odometry"):
        diag = topic_diag.get(key)
        if isinstance(diag, dict):
            matched = diag.get("matched") or diag.get("expected")
            if isinstance(matched, str) and matched.strip():
                return matched.strip()
    env_topic = os.getenv("WAREHOUSE_ODOMETRY_TOPIC", "").strip()
    if env_topic:
        return env_topic
    return "/warehouse/drone/odometry"


def odometry_source_label(*, gazebo_sim: bool | None = None) -> str:
    sim = _gazebo_sim_enabled() if gazebo_sim is None else gazebo_sim
    return "sim_odom" if sim else "vslam_odom"


def odometry_display_name(
    components: dict[str, Any],
    *,
    gazebo_sim: bool | None = None,
) -> str:
    source = components.get("odometry_source")
    if not isinstance(source, str) or not source.strip():
        source = odometry_source_label(gazebo_sim=gazebo_sim)
    topic = components.get("odometry_topic")
    if not isinstance(topic, str) or not topic.strip():
        topic = odometry_topic_path(components)
    return f"{source} ({topic})"


def _topic_diag_entry(components: dict[str, Any], key: str) -> dict[str, Any] | None:
    topic_diag_raw = components.get("topic_diagnostics")
    topic_diag = topic_diag_raw if isinstance(topic_diag_raw, dict) else {}
    diag = topic_diag.get(key)
    return diag if isinstance(diag, dict) else None


def odometry_topic_is_live(
    components: dict[str, Any],
    *,
    strict: bool = True,
) -> bool:
    from backend.modules.warehouse.service.readiness_result import topic_is_strictly_live

    for key in ("visual_slam_odom", "local_odometry"):
        diag = _topic_diag_entry(components, key)
        if strict:
            if topic_is_strictly_live(diag):
                return True
        elif isinstance(diag, dict) and diag.get("healthy"):
            return True
    return False


@dataclass(frozen=True)
class LocalOdometryHealth:
    fresh: bool
    unreadable: bool
    topic_live: bool
    age_s: float | None
    display_name: str


def evaluate_local_odometry(
    components: dict[str, Any],
    *,
    max_age_s: float | None = None,
    gazebo_sim: bool | None = None,
    strict_topic: bool = True,
) -> LocalOdometryHealth:
    max_age = default_odometry_max_age_s() if max_age_s is None else max_age_s
    unreadable = bool(components.get("odometry_state_unreadable"))
    odom_state_raw = components.get("local_odometry_state")
    odom_state = odom_state_raw if isinstance(odom_state_raw, dict) else {}
    age_s = odometry_state_age_s(odom_state)
    state_fresh = odometry_state_is_fresh(odom_state, max_age_s=max_age) if odom_state else False
    topic_live = odometry_topic_is_live(components, strict=strict_topic)
    fresh = (state_fresh or topic_live) and not unreadable
    return LocalOdometryHealth(
        fresh=fresh,
        unreadable=unreadable,
        topic_live=topic_live,
        age_s=age_s,
        display_name=odometry_display_name(components, gazebo_sim=gazebo_sim),
    )


def _default_startup_grace_s() -> float:
    if _gazebo_sim_enabled():
        return _float_env("WAREHOUSE_RUNTIME_STARTUP_GRACE_S", 45.0)
    return _float_env("WAREHOUSE_RUNTIME_STARTUP_GRACE_S", 15.0)


def _topic_diag_live(diag: object) -> bool:
    if not isinstance(diag, dict):
        return False
    if diag.get("healthy"):
        return True
    state = diag.get("readiness_state")
    return state in {
        "ok",
        "ok_via_messages",
        "ok_graph_presence",
        "shallow_present",
    }


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_odometry_timestamp(payload: dict[str, Any]) -> float | None:
    updated_mono = payload.get("updated_at_monotonic")
    if isinstance(updated_mono, (int, float)):
        return float(updated_mono)

    stamp = payload.get("timestamp_utc")
    if isinstance(stamp, str) and stamp.strip():
        try:
            normalized = stamp.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            pass

    source_stamp = payload.get("source_stamp_sec")
    if isinstance(source_stamp, (int, float)):
        return float(source_stamp)

    return None


def odometry_state_age_s(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    updated_mono = payload.get("updated_at_monotonic")
    if isinstance(updated_mono, (int, float)):
        return max(0.0, time.monotonic() - float(updated_mono))

    stamp_ts = _parse_odometry_timestamp(payload)
    if stamp_ts is None:
        return None
    if payload.get("updated_at_monotonic") is None and payload.get("source_stamp_sec") is not None:
        return None
    return max(0.0, time.time() - stamp_ts)


def odometry_state_is_fresh(
    payload: dict[str, Any] | None,
    *,
    max_age_s: float,
) -> bool:
    age = odometry_state_age_s(payload)
    if age is None:
        return False
    return age <= max_age_s


@dataclass
class WarehouseRuntimeSafetyTracker:
    """Tracks transient sensor gaps vs sustained localization loss during flight."""

    mission_started_at: float = field(default_factory=time.monotonic)
    startup_grace_s: float = field(default_factory=_default_startup_grace_s)
    odometry_stale_s: float = field(default_factory=_default_odometry_stale_s)
    vslam_recovery_grace_s: float = field(
        default_factory=lambda: _float_env("WAREHOUSE_RUNTIME_VSLAM_RECOVERY_GRACE_S", 4.0)
    )
    _vslam_loss_started_at: float | None = field(default=None, init=False, repr=False)
    _last_deep_probe_at: float = field(default=0.0, init=False, repr=False)
    deep_probe_interval_s: float = field(
        default_factory=lambda: _float_env("WAREHOUSE_RUNTIME_DEEP_HEALTH_INTERVAL_S", 12.0)
    )

    def mission_elapsed_s(self) -> float:
        return max(0.0, time.monotonic() - self.mission_started_at)

    def in_startup_grace(self) -> bool:
        return self.mission_elapsed_s() < self.startup_grace_s

    def should_run_deep_health_probe(self) -> bool:
        return (time.monotonic() - self._last_deep_probe_at) >= self.deep_probe_interval_s

    def mark_deep_probe_ran(self) -> None:
        self._last_deep_probe_at = time.monotonic()

    def reset_for_takeoff(self) -> None:
        """Restart startup grace from arm/takeoff, not mission planning time."""
        self.mission_started_at = time.monotonic()
        self._vslam_loss_started_at = None
        self._last_deep_probe_at = 0.0

    def evaluate(
        self,
        components: dict[str, Any],
        *,
        deep_health: bool = False,
        min_localization_confidence: float = 0.5,
        min_obstacle_distance_m: float = 0.6,
        min_ceiling_distance_m: float = 0.5,
    ) -> WarehouseSafetyDecision:
        if components.get("ros_bridge_heartbeat") is False:
            return WarehouseSafetyDecision(False, "land", "ros_bridge_heartbeat_lost")

        odom = evaluate_local_odometry(
            components,
            max_age_s=self.odometry_stale_s,
            strict_topic=True,
        )
        odom_state_raw = components.get("local_odometry_state")
        odom_state = odom_state_raw if isinstance(odom_state_raw, dict) else {}
        odom_age_s = odom.age_s
        odom_fresh = odom.fresh
        odom_topic = odometry_topic_path(components)

        topic_diag_raw = components.get("topic_diagnostics")
        topic_diag = topic_diag_raw if isinstance(topic_diag_raw, dict) else {}
        vslam_diag = topic_diag.get("visual_slam_odom")
        vslam_topic_missing = (
            deep_health
            and isinstance(vslam_diag, dict)
            and vslam_diag.get("readiness_state") == "topic_missing"
        )
        vslam_topic_stale = (
            deep_health
            and isinstance(vslam_diag, dict)
            and not vslam_diag.get("healthy")
            and vslam_diag.get("readiness_state") in {"no_messages", "unhealthy"}
        )

        explicit_tracking_lost = odom_state.get("slam_tracking_ok") is False

        if odom.unreadable:
            return WarehouseSafetyDecision(
                False,
                "hover",
                "odometry_state_unreadable",
                {
                    "topic": odom_topic,
                    "display_name": odom.display_name,
                    "max_age_s": self.odometry_stale_s,
                },
            )

        if self.in_startup_grace():
            if not odom_fresh and not odom_state:
                return WarehouseSafetyDecision(
                    True,
                    "continue",
                    None,
                    {
                        "phase": "startup_grace",
                        "elapsed_s": round(self.mission_elapsed_s(), 2),
                    },
                )
            if explicit_tracking_lost:
                return WarehouseSafetyDecision(
                    False,
                    "return_or_land",
                    "vslam_tracking_lost",
                    {"phase": "startup_grace", "odometry_age_s": odom_age_s},
                )
            if not odom_fresh:
                return WarehouseSafetyDecision(
                    False,
                    "hover",
                    "odometry_stale",
                    {
                        "phase": "startup_grace",
                        "topic": odom_topic,
                        "display_name": odom.display_name,
                        "odometry_age_s": round(odom_age_s or 0.0, 3),
                        "max_age_s": self.odometry_stale_s,
                    },
                )
            return WarehouseSafetyDecision(
                True,
                "continue",
                None,
                {"phase": "startup_grace", "odometry_age_s": odom_age_s},
            )

        if vslam_topic_missing and not odom_fresh:
            return WarehouseSafetyDecision(
                False,
                "return_or_land",
                "odometry_topic_unavailable",
                {"topic": odom_topic, "display_name": odom.display_name},
            )

        if not odom_fresh:
            if odom_age_s is None and not odom_state:
                if deep_health and vslam_topic_stale:
                    return WarehouseSafetyDecision(
                        False,
                        "hover",
                        "odometry_topic_stale",
                        {
                            "topic": odom_topic,
                            "display_name": odom.display_name,
                            "topic_diagnostics": vslam_diag,
                        },
                    )
                return WarehouseSafetyDecision(
                    False,
                    "hover",
                    "odometry_unavailable",
                    {
                        "topic": odom_topic,
                        "display_name": odom.display_name,
                        "detail": "no odometry state published",
                    },
                )
            action = "hover" if (odom_age_s or 0.0) <= (self.odometry_stale_s * 1.5) else "return_or_land"
            return WarehouseSafetyDecision(
                False,
                action,
                "odometry_stale",
                {
                    "topic": odom_topic,
                    "display_name": odom.display_name,
                    "odometry_age_s": round(odom_age_s or 0.0, 3),
                    "max_age_s": self.odometry_stale_s,
                },
            )

        if explicit_tracking_lost:
            now = time.monotonic()
            if self.vslam_recovery_grace_s <= 0:
                return WarehouseSafetyDecision(
                    False,
                    "return_or_land",
                    "vslam_tracking_lost",
                    {"odometry_age_s": round(odom_age_s or 0.0, 3)},
                )
            if self._vslam_loss_started_at is None:
                self._vslam_loss_started_at = now
            elif (now - self._vslam_loss_started_at) >= self.vslam_recovery_grace_s:
                return WarehouseSafetyDecision(
                    False,
                    "return_or_land",
                    "vslam_tracking_lost",
                    {
                        "odometry_age_s": round(odom_age_s or 0.0, 3),
                        "loss_duration_s": round(now - self._vslam_loss_started_at, 3),
                    },
                )
            return WarehouseSafetyDecision(
                True,
                "continue",
                None,
                {
                    "phase": "vslam_recovery_grace",
                    "loss_duration_s": round(now - self._vslam_loss_started_at, 3),
                },
            )

        self._vslam_loss_started_at = None

        runtime_components = dict(components)
        if odom_fresh:
            runtime_components["slam_tracking_ok"] = True
            runtime_components.setdefault("visual_slam", True)

        return evaluate_warehouse_runtime_safety(
            runtime_components,
            min_localization_confidence=min_localization_confidence,
            min_obstacle_distance_m=min_obstacle_distance_m,
            min_ceiling_distance_m=min_ceiling_distance_m,
        )

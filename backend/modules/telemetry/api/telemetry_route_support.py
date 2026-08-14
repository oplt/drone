from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

connect_lock = asyncio.Lock()
_manual_control_tasks: set[asyncio.Task] = set()

VELOCITY_STEP_MPS = 1.0
YAW_RATE_DPS = 30.0
ALTITUDE_STEP_MPS = 0.8
RECENT_TELEMETRY_THRESHOLD_SEC = 15.0

COMMAND_VELOCITY_MAP: dict[str, tuple[float, float, float, float]] = {
    "forward": (VELOCITY_STEP_MPS, 0.0, 0.0, 0.0),
    "backward": (-VELOCITY_STEP_MPS, 0.0, 0.0, 0.0),
    "left": (0.0, -VELOCITY_STEP_MPS, 0.0, 0.0),
    "right": (0.0, VELOCITY_STEP_MPS, 0.0, 0.0),
    "yaw_left": (0.0, 0.0, 0.0, -YAW_RATE_DPS),
    "yaw_right": (0.0, 0.0, 0.0, YAW_RATE_DPS),
    "up": (0.0, 0.0, -ALTITUDE_STEP_MPS, 0.0),
    "down": (0.0, 0.0, ALTITUDE_STEP_MPS, 0.0),
    "hold": (0.0, 0.0, 0.0, 0.0),
}

OPS_HEALTH_QUEUE_LABELS: dict[str, str] = {
    "flight events": "db_event_queue",
    "mission lifecycle": "db_lifecycle_queue",
    "raw ingest": "raw_event_queue",
}


def track_background_task(task: asyncio.Task) -> None:
    _manual_control_tasks.add(task)
    task.add_done_callback(_manual_control_tasks.discard)


def expected_drone_connect_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "gps home is required" in text
        or "home fallback is disabled" in text
        or "heartbeat" in text
        or "timed out" in text
        or "timeout" in text
    )


def queue_snapshot(runtime_metrics: Mapping[str, Any], prefix: str) -> dict[str, float | int]:
    depth = int(runtime_metrics.get(f"{prefix}_depth", 0) or 0)
    capacity = int(runtime_metrics.get(f"{prefix}_capacity", 0) or 0)
    utilization_pct = round((depth / capacity) * 100, 1) if capacity > 0 else 0.0
    return {
        "depth": depth,
        "capacity": capacity,
        "utilization_pct": utilization_pct,
    }


def telemetry_update_age(last_update: float, now: float) -> float | None:
    last_update = float(last_update or 0.0)
    return round(max(0.0, now - last_update), 1) if last_update > 0 else None


def velocity_for_manual_command(
    command: str, phase: str
) -> tuple[float, float, float, float]:
    if phase == "stop":
        return (0.0, 0.0, 0.0, 0.0)
    return COMMAND_VELOCITY_MAP.get(command, (0.0, 0.0, 0.0, 0.0))


def collect_ops_health_alerts(
    *,
    telemetry: Mapping[str, Any],
    has_recent_update: bool,
    runtime_metrics: Mapping[str, Any],
    labeled_queue_snapshots: Mapping[str, Mapping[str, float | int]],
    shadow_report: Mapping[str, Any],
    video_status: Mapping[str, Any],
) -> list[str]:
    alerts: list[str] = []
    if not telemetry["running"]:
        alerts.append("Telemetry runtime is not running.")
    elif not telemetry["source_connected"]:
        alerts.append("Telemetry runtime is up, but the drone data source is disconnected.")
    elif not has_recent_update:
        alerts.append("Telemetry updates are stale.")

    if runtime_metrics.get("dropped_db_events", 0):
        alerts.append("Runtime dropped DB events under queue pressure.")

    for label, snapshot in labeled_queue_snapshots.items():
        if snapshot["utilization_pct"] >= 80:
            alerts.append(f"{label.capitalize()} queue utilization is above 80%.")

    if shadow_report["shadow_mode_active"] and shadow_report["old_path"]["writes_failed"] > 0:
        alerts.append("Shadow-mode writes are failing and need investigation.")

    if video_status.get("available") and not bool(video_status.get("healthy", False)):
        alerts.append("Video stream health is degraded.")
    return alerts


def ops_health_overall_status(alerts: list[str], source_connected: bool) -> str:
    if alerts:
        return "offline" if not source_connected else "degraded"
    return "healthy"

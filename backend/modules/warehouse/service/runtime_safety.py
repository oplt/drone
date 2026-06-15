from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.warehouse.service.safety import (
    WarehouseSafetyDecision,
    evaluate_warehouse_runtime_safety,
)

_MAX_STATE_FILE_BYTES = 1_000_000
_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "authorization", "cookie", "key")


@dataclass(frozen=True)
class OdometryStateRead:
    payload: dict[str, Any] = field(default_factory=dict)
    unreadable: bool = False
    error: str | None = None


def _redact(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "<redacted-depth>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in _SENSITIVE_KEY_PARTS):
                result[key_text] = "<redacted>"
            else:
                result[key_text] = _redact(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_redact(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, tuple):
        return tuple(_redact(item, depth=depth + 1) for item in value[:50])
    return value


def _setting_float(name: str, default: float) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError, OverflowError):
        return default
    return value if value == value and abs(value) != float("inf") else default


def read_odometry_state_file() -> OdometryStateRead:
    path_raw = str(getattr(settings, "WAREHOUSE_ODOMETRY_STATE_PATH", "") or "").strip()
    if not path_raw:
        return OdometryStateRead()
    path = Path(path_raw).expanduser()
    try:
        if not path.exists() or not path.is_file():
            return OdometryStateRead()
        if path.stat().st_size > _MAX_STATE_FILE_BYTES:
            return OdometryStateRead(unreadable=True, error="odometry state file is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return OdometryStateRead(unreadable=True, error=str(exc)[:240])
    return OdometryStateRead(payload=payload if isinstance(payload, dict) else {})


def merge_runtime_odometry_components(components: dict[str, Any]) -> dict[str, Any]:
    merged = dict(components)
    state = merged.get("local_odometry_state")
    if isinstance(state, dict):
        merged.update({k: v for k, v in state.items() if k not in merged})
    return merged


class WarehouseRuntimeSafetyTracker:
    def __init__(self) -> None:
        self._last_deep_probe_s = 0.0
        self._lock = threading.Lock()

    def reset_for_takeoff(self) -> None:
        with self._lock:
            self._last_deep_probe_s = 0.0

    def should_run_deep_health_probe(self) -> bool:
        interval = max(0.5, _setting_float("warehouse_deep_health_probe_interval_s", 5.0))
        with self._lock:
            return time.monotonic() - self._last_deep_probe_s >= interval

    def mark_deep_probe_ran(self) -> None:
        with self._lock:
            self._last_deep_probe_s = time.monotonic()

    def evaluate(
        self,
        components: dict[str, Any],
        *,
        deep_health: bool,
        min_localization_confidence: float,
        min_obstacle_distance_m: float,
        min_ceiling_distance_m: float,
    ) -> WarehouseSafetyDecision:
        merged = merge_runtime_odometry_components(components)
        state_read: OdometryStateRead | None = None
        if deep_health:
            state_read = read_odometry_state_file()
            if state_read.payload:
                merged = merge_runtime_odometry_components({**state_read.payload, **merged})

        class Health:
            localization_confidence = merged.get("localization_confidence")
            nearest_obstacle_m = merged.get("obstacle_distance_m")
            ceiling_distance_m = merged.get("ceiling_distance_m")

        if state_read is not None and state_read.unreadable:
            return WarehouseSafetyDecision(
                safe=False,
                reason="odometry_state_unreadable",
                action="hold_or_land",
                details={"error": state_read.error},
            )

        if merged.get("localization_ok") is False or merged.get("slam_tracking_ok") is False:
            return WarehouseSafetyDecision(
                safe=False,
                reason="localization_unhealthy",
                action="return_or_relocalize",
                details={
                    "localization_ok": merged.get("localization_ok"),
                    "slam_tracking_ok": merged.get("slam_tracking_ok"),
                    "components": _redact({
                        k: merged.get(k)
                        for k in (
                            "localization_confidence",
                            "obstacle_distance_m",
                            "ceiling_distance_m",
                            "odometry_healthy",
                        )
                        if k in merged
                    }),
                },
            )
        return evaluate_warehouse_runtime_safety(
            health=Health(),
            battery_pct=merged.get("battery_pct"),
            min_localization_confidence=min_localization_confidence,
            min_obstacle_distance_m=min_obstacle_distance_m,
            min_ceiling_distance_m=min_ceiling_distance_m,
        )

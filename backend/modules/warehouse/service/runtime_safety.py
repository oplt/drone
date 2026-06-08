from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.warehouse.service.safety import (
    WarehouseSafetyDecision,
    evaluate_warehouse_runtime_safety,
)


@dataclass(frozen=True)
class OdometryStateRead:
    payload: dict[str, Any] = field(default_factory=dict)
    unreadable: bool = False
    error: str | None = None


def read_odometry_state_file() -> OdometryStateRead:
    path_raw = str(getattr(settings, "WAREHOUSE_ODOMETRY_STATE_PATH", "") or "").strip()
    if not path_raw:
        return OdometryStateRead()
    path = Path(path_raw)
    if not path.exists():
        return OdometryStateRead()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return OdometryStateRead(unreadable=True, error=str(exc))
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

    def reset_for_takeoff(self) -> None:
        self._last_deep_probe_s = 0.0

    def should_run_deep_health_probe(self) -> bool:
        interval = float(os.getenv("WAREHOUSE_DEEP_HEALTH_PROBE_INTERVAL_S", "5"))
        return time.monotonic() - self._last_deep_probe_s >= max(0.5, interval)

    def mark_deep_probe_ran(self) -> None:
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
        del deep_health

        class Health:
            localization_confidence = components.get("localization_confidence")
            nearest_obstacle_m = components.get("obstacle_distance_m")
            ceiling_distance_m = components.get("ceiling_distance_m")

        if (
            components.get("localization_ok") is False
            or components.get("slam_tracking_ok") is False
        ):
            return WarehouseSafetyDecision(
                safe=False,
                reason="localization_unhealthy",
                action="return_or_relocalize",
                details={"components": components},
            )
        return evaluate_warehouse_runtime_safety(
            health=Health(),
            min_localization_confidence=min_localization_confidence,
            min_obstacle_distance_m=min_obstacle_distance_m,
            min_ceiling_distance_m=min_ceiling_distance_m,
        )

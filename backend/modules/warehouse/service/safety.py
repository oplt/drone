from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WarehouseSafetyDecision:
    safe: bool
    reason: str | None = None
    action: str = "continue"
    details: dict[str, Any] = field(default_factory=dict)


def evaluate_warehouse_runtime_safety(
    *,
    health: Any | None = None,
    battery_pct: float | None = None,
    min_localization_confidence: float = 0.5,
    min_obstacle_distance_m: float = 0.5,
    min_ceiling_distance_m: float = 0.2,
    **_: Any,
) -> WarehouseSafetyDecision:
    confidence = getattr(health, "localization_confidence", None)
    if confidence is not None and float(confidence) < float(min_localization_confidence):
        return WarehouseSafetyDecision(
            safe=False,
            reason="localization_confidence_low",
            action="return_or_relocalize",
            details={"localization_confidence": float(confidence)},
        )
    obstacle = getattr(health, "nearest_obstacle_m", None)
    if obstacle is not None and float(obstacle) < float(min_obstacle_distance_m):
        return WarehouseSafetyDecision(
            safe=False,
            reason="obstacle_too_close",
            action="land",
            details={"nearest_obstacle_m": float(obstacle)},
        )
    ceiling = getattr(health, "ceiling_distance_m", None)
    if ceiling is not None and float(ceiling) < float(min_ceiling_distance_m):
        return WarehouseSafetyDecision(
            safe=False,
            reason="ceiling_too_close",
            action="land",
            details={"ceiling_distance_m": float(ceiling)},
        )
    if battery_pct is not None and float(battery_pct) < 10.0:
        return WarehouseSafetyDecision(
            safe=False,
            reason="battery_critical",
            action="land",
            details={"battery_pct": float(battery_pct)},
        )
    return WarehouseSafetyDecision(safe=True)


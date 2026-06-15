from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WarehouseSafetyDecision:
    safe: bool
    reason: str | None = None
    action: str = "continue"
    details: dict[str, Any] = field(default_factory=dict)


def _finite_float(value: Any, *, field_name: str) -> tuple[float | None, WarehouseSafetyDecision | None]:
    if value is None:
        return None, None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None, WarehouseSafetyDecision(
            safe=False,
            reason="invalid_health_value",
            action="hold_or_land",
            details={"field": field_name},
        )
    if not math.isfinite(number):
        return None, WarehouseSafetyDecision(
            safe=False,
            reason="invalid_health_value",
            action="hold_or_land",
            details={"field": field_name},
        )
    return number, None


def _threshold(value: Any, *, default: float, minimum: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(minimum, number)


def evaluate_warehouse_runtime_safety(
    *,
    health: Any | None = None,
    battery_pct: float | None = None,
    min_localization_confidence: float = 0.5,
    min_obstacle_distance_m: float = 0.5,
    min_ceiling_distance_m: float = 0.2,
    **_: Any,
) -> WarehouseSafetyDecision:
    min_confidence = _threshold(min_localization_confidence, default=0.5, minimum=0.0)
    min_obstacle = _threshold(min_obstacle_distance_m, default=0.5, minimum=0.0)
    min_ceiling = _threshold(min_ceiling_distance_m, default=0.2, minimum=0.0)

    confidence, invalid = _finite_float(
        getattr(health, "localization_confidence", None),
        field_name="localization_confidence",
    )
    if invalid is not None:
        return invalid
    if confidence is not None and confidence < min_confidence:
        return WarehouseSafetyDecision(
            safe=False,
            reason="localization_confidence_low",
            action="return_or_relocalize",
            details={"localization_confidence": confidence, "minimum": min_confidence},
        )

    obstacle, invalid = _finite_float(
        getattr(health, "nearest_obstacle_m", None),
        field_name="nearest_obstacle_m",
    )
    if invalid is not None:
        return invalid
    if obstacle is not None and obstacle < min_obstacle:
        return WarehouseSafetyDecision(
            safe=False,
            reason="obstacle_too_close",
            action="land",
            details={"nearest_obstacle_m": obstacle, "minimum": min_obstacle},
        )

    ceiling, invalid = _finite_float(
        getattr(health, "ceiling_distance_m", None),
        field_name="ceiling_distance_m",
    )
    if invalid is not None:
        return invalid
    if ceiling is not None and ceiling < min_ceiling:
        return WarehouseSafetyDecision(
            safe=False,
            reason="ceiling_too_close",
            action="land",
            details={"ceiling_distance_m": ceiling, "minimum": min_ceiling},
        )

    battery, invalid = _finite_float(battery_pct, field_name="battery_pct")
    if invalid is not None:
        return invalid
    if battery is not None and battery < 10.0:
        return WarehouseSafetyDecision(
            safe=False,
            reason="battery_critical",
            action="land",
            details={"battery_pct": battery, "minimum": 10.0},
        )

    return WarehouseSafetyDecision(safe=True)

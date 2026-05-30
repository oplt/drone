from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WarehouseSafetyDecision:
    safe: bool
    action: str
    reason: str | None = None
    details: dict[str, object] | None = None


def _num(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def evaluate_warehouse_runtime_safety(
    components: dict[str, Any],
    *,
    min_localization_confidence: float = 0.5,
    min_obstacle_distance_m: float = 0.6,
    min_ceiling_distance_m: float = 0.5,
) -> WarehouseSafetyDecision:
    if components.get("ros_bridge_heartbeat") is False:
        return WarehouseSafetyDecision(False, "land", "ros_bridge_heartbeat_lost")
    if components.get("slam_tracking_ok", components.get("visual_slam")) is False:
        return WarehouseSafetyDecision(False, "return_or_land", "vslam_tracking_lost")

    obstacle_distance = _num(components.get("obstacle_distance_m"))
    if obstacle_distance is not None and obstacle_distance < float(min_obstacle_distance_m):
        return WarehouseSafetyDecision(
            False,
            "hover",
            "obstacle_clearance_breach",
            {"obstacle_distance_m": obstacle_distance},
        )

    ceiling_distance = _num(components.get("ceiling_distance_m"))
    if ceiling_distance is not None and ceiling_distance < float(min_ceiling_distance_m):
        return WarehouseSafetyDecision(
            False,
            "land",
            "ceiling_margin_breach",
            {"ceiling_distance_m": ceiling_distance},
        )

    confidence = _num(components.get("localization_confidence"))
    if confidence is not None and confidence < float(min_localization_confidence):
        return WarehouseSafetyDecision(
            False,
            "return_or_relocalize",
            "localization_confidence_low",
            {"localization_confidence": confidence},
        )

    return WarehouseSafetyDecision(True, "continue")

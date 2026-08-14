from __future__ import annotations

from dataclasses import dataclass

from backend.core.tokens import safe_token
from backend.modules.warehouse.service.startup_timing_hooks import (
    active_mapping_startup_timing_safe,
    begin_mapping_startup_safe,
    note_mapping_startup_safe,
)


def safe_token_value(raw: object) -> str:
    return safe_token(raw)


def normalize_angle_deg(value: float) -> float:
    normalized = float(value) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def angle_delta_deg(start_deg: float, end_deg: float) -> float:
    return normalize_angle_deg(float(end_deg) - float(start_deg))


def interpolate_yaw_deg(start_deg: float | None, end_deg: float | None, t: float) -> float | None:
    if start_deg is None and end_deg is None:
        return None
    if start_deg is None:
        return normalize_angle_deg(float(end_deg))  # type: ignore[arg-type]
    if end_deg is None:
        return normalize_angle_deg(float(start_deg))
    return normalize_angle_deg(
        float(start_deg) + (angle_delta_deg(float(start_deg), float(end_deg)) * float(t))
    )


def dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def begin_mapping_startup_timing(*, mission_start_monotonic: float) -> None:
    begin_mapping_startup_safe(mission_start_monotonic=mission_start_monotonic)


def note_mapping_startup(mark: str) -> None:
    note_mapping_startup_safe(mark)


def active_mapping_startup_timing():
    return active_mapping_startup_timing_safe()


@dataclass(frozen=True)
class WarehouseExecutionFrame:
    """ENU offset between the planner origin and live odom measured at takeoff."""

    x_offset_m: float
    y_offset_m: float
    z_offset_m: float

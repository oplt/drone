from __future__ import annotations

import os
from enum import StrEnum

from backend.modules.warehouse.service.bridge_flow import resolve_warehouse_bridge_flow


class LocalizationMode(StrEnum):
    GAZEBO_GROUND_TRUTH = "gazebo_ground_truth"
    VISUAL_SLAM = "visual_slam"


def resolve_localization_mode() -> LocalizationMode:
    raw = os.getenv("WAREHOUSE_LOCALIZATION_MODE", "").strip().lower()
    if raw in {"gazebo_ground_truth", "gazebo_gt", "sim", "gazebo"}:
        return LocalizationMode.GAZEBO_GROUND_TRUTH
    if raw in {"visual_slam", "vslam", "vio", "slam"}:
        return LocalizationMode.VISUAL_SLAM
    if resolve_warehouse_bridge_flow().name == "gazebo":
        return LocalizationMode.GAZEBO_GROUND_TRUTH
    return LocalizationMode.VISUAL_SLAM


def tracking_status_for_mode(
    mode: LocalizationMode,
    *,
    tracking_ok: bool,
    failure: str | None = None,
) -> str:
    if mode == LocalizationMode.GAZEBO_GROUND_TRUTH:
        if tracking_ok:
            return "GAZEBO_GROUND_TRUTH_OK"
        return failure or "GAZEBO_GROUND_TRUTH_UNAVAILABLE"
    if tracking_ok:
        return "TRACKING_OK"
    return failure or "TRACKING_LOST"


def localization_mode_env_value(mode: LocalizationMode | None = None) -> str:
    selected = mode or resolve_localization_mode()
    return selected.value

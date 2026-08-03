"""Explicit, reviewable agriculture capture presets."""

from copy import deepcopy
from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "early_stand_count": {
        "sensor_inventory": ["rgb"], "target_gsd_cm": 1.5, "speed_mps": 3.0,
        "front_overlap_pct": 80.0, "side_overlap_pct": 70.0,
        "requested_analyses": ["quality", "stand_count", "gaps", "double_plants"],
    },
    "rgb_weed_water": {
        "sensor_inventory": ["rgb"], "target_gsd_cm": 2.0, "speed_mps": 5.0,
        "front_overlap_pct": 70.0, "side_overlap_pct": 60.0,
        "requested_analyses": ["quality", "weed", "water", "coverage"],
    },
    "repeat_monitoring": {
        "sensor_inventory": ["rgb"], "target_gsd_cm": 2.0, "speed_mps": 4.0,
        "front_overlap_pct": 75.0, "side_overlap_pct": 65.0,
        "requested_analyses": ["quality", "coverage", "temporal_change"],
        "repeat_interval_days": 7,
    },
    "multispectral_thermal": {
        "sensor_inventory": ["multispectral", "thermal"], "target_gsd_cm": 3.0, "speed_mps": 3.0,
        "front_overlap_pct": 80.0, "side_overlap_pct": 70.0,
        "requested_analyses": ["quality", "coverage", "stress", "thermal_water"],
    },
}


def preset_values(name: str) -> dict[str, Any]:
    try:
        return deepcopy(PRESETS[name])
    except KeyError as exc:
        raise ValueError(f"Unknown agriculture preset: {name}") from exc

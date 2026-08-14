from __future__ import annotations

import math


def estimate_camera_trigger_distance_m(
    *,
    altitude_agl_m: float,
    overlap_pct: float,
    camera_fov_v_deg: float = 62.0,
    min_spacing_m: float = 2.0,
    max_spacing_m: float = 25.0,
) -> float:
    """Estimate camera trigger distance from altitude and overlap target."""
    overlap_fraction = max(0.01, min(0.95, float(overlap_pct) / 100.0))
    footprint_m = (
        2.0 * float(altitude_agl_m) * math.tan(math.radians(float(camera_fov_v_deg) / 2.0))
    )
    spacing_m = footprint_m * (1.0 - overlap_fraction)
    return max(float(min_spacing_m), min(float(max_spacing_m), float(spacing_m)))

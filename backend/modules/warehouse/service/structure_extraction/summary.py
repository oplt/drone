"""Structure extraction summary helpers."""

from __future__ import annotations

from typing import Any

from .models import StructureExtractionParams


def _params_to_dict(params: StructureExtractionParams) -> dict[str, Any]:
    return {
        "voxel_m": params.voxel_m,
        "grid_res_m": params.grid_res_m,
        "floor_margin_m": params.floor_margin_m,
        "ceiling_max_m": params.ceiling_max_m,
        "min_aisle_width_m": params.min_aisle_width_m,
        "min_rack_length_m": params.min_rack_length_m,
        "bin_pitch_m": params.bin_pitch_m,
        "shelf_min_spacing_m": params.shelf_min_spacing_m,
        "max_shelf_levels": params.max_shelf_levels,
        "max_bins_per_rack_face": params.max_bins_per_rack_face,
        "min_target_spacing_m": params.min_target_spacing_m,
        "review_clearance_m": params.review_clearance_m,
        "standoff_m": params.standoff_m,
        "drone_radius_m": params.drone_radius_m,
        "clearance_margin_m": params.clearance_margin_m,
        "min_surface_points": params.min_surface_points,
        "rack_template_version_id": params.rack_template_version_id,
        "rack_template_bin_count": params.rack_template_bin_count,
        "rack_template_bay_width_m": params.rack_template_bay_width_m,
        "rack_template_shelf_levels_m": list(params.rack_template_shelf_levels_m),
        "axis_deg": params.axis_deg,
    }

from __future__ import annotations

import math
from typing import Any

import numpy as np

from backend.modules.warehouse.models import (
    WarehouseBin,
    WarehouseRack,
    WarehouseRackTemplate,
    WarehouseRackTemplateVersion,
    WarehouseShelf,
)


def template_params_payload(version: WarehouseRackTemplateVersion) -> dict[str, Any]:
    levels = [float(value) for value in version.shelf_heights_json or []]
    return {
        "rack_template_version_id": int(version.id),
        "rack_template_bay_width_m": float(version.bay_width_m),
        "rack_template_bin_count": int(version.bin_count) if version.bin_count else None,
        "rack_template_shelf_levels_m": levels,
        "bin_pitch_m": float(version.bin_pitch_m),
        "standoff_m": float(version.preferred_standoff_m),
    }


def template_summary(
    template: WarehouseRackTemplate,
    version: WarehouseRackTemplateVersion,
) -> dict[str, Any]:
    return {
        "template_id": int(template.id),
        "template_version_id": int(version.id),
        "name": template.name,
        "rack_type": template.rack_type,
        "version": int(version.version),
        "bay_width_m": float(version.bay_width_m),
        "shelf_heights_m": [float(value) for value in version.shelf_heights_json or []],
        "bin_pitch_m": float(version.bin_pitch_m),
        "bin_count": int(version.bin_count) if version.bin_count else None,
        "left_face_naming": version.left_face_naming,
        "right_face_naming": version.right_face_naming,
        "barcode_scan_side": version.barcode_scan_side,
        "preferred_standoff_m": float(version.preferred_standoff_m),
        "min_scanner_angle_deg": float(version.min_scanner_angle_deg),
    }


def _target_point(geometry: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("target_point", "center", "center_point"):
        value = geometry.get(key) if isinstance(geometry, dict) else None
        if isinstance(value, dict) and {"x_m", "y_m"}.issubset(value):
            return value
    return None


def _fit_axis(points: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    if not points:
        return [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]
    xyz = np.array(
        [
            [
                float(point.get("x_m") or 0.0),
                float(point.get("y_m") or 0.0),
                float(point.get("z_m") or 0.0),
            ]
            for point in points
        ],
        dtype=np.float64,
    )
    origin = xyz.mean(axis=0)
    if xyz.shape[0] < 2:
        return origin.tolist(), [1.0, 0.0, 0.0]
    centered = xyz[:, :2] - origin[:2]
    cov = np.cov(centered.T)
    if not np.all(np.isfinite(cov)):
        return origin.tolist(), [1.0, 0.0, 0.0]
    eigvals, eigvecs = np.linalg.eigh(cov)
    axis_xy = eigvecs[:, int(np.argmax(eigvals))]
    axis = [float(axis_xy[0]), float(axis_xy[1]), 0.0]
    length = math.hypot(axis[0], axis[1])
    if length <= 1e-9:
        return origin.tolist(), [1.0, 0.0, 0.0]
    return origin.tolist(), [axis[0] / length, axis[1] / length, 0.0]


def fitted_transform_from_bins(
    *,
    bins: list[WarehouseBin],
) -> dict[str, Any]:
    points = [
        point
        for bin_row in bins
        if (point := _target_point(dict(bin_row.geometry_json or {}))) is not None
    ]
    origin, axis = _fit_axis(points)
    yaw_rad = math.atan2(axis[1], axis[0])
    return {
        "origin": {
            "frame_id": "warehouse_map",
            "x_m": round(float(origin[0]), 3),
            "y_m": round(float(origin[1]), 3),
            "z_m": round(float(origin[2]), 3),
        },
        "axis": {
            "x": round(float(axis[0]), 6),
            "y": round(float(axis[1]), 6),
            "z": 0.0,
        },
        "yaw_deg": round(math.degrees(yaw_rad), 3),
    }


def apply_template_to_rack_geometry(
    *,
    rack: WarehouseRack,
    shelves: list[WarehouseShelf],
    bins_by_shelf: dict[int, list[WarehouseBin]],
    template: WarehouseRackTemplate,
    version: WarehouseRackTemplateVersion,
) -> dict[str, Any]:
    all_bins = [bin_row for rows in bins_by_shelf.values() for bin_row in rows]
    fitted = fitted_transform_from_bins(bins=all_bins)
    origin = fitted["origin"]
    axis = fitted["axis"]
    shelf_heights = [float(value) for value in version.shelf_heights_json or []]
    bin_pitch = float(version.bin_pitch_m)
    template_meta = template_summary(template, version)

    rack.template_version_id = int(version.id)
    rack.fitted_transform_json = fitted
    rack.template_fit_json = {
        "template": template_meta,
        "snapped_bin_count": len(all_bins),
        "source": "operator_assignment",
    }
    rack_geometry = dict(rack.geometry_json or {})
    rack_geometry["template"] = template_meta
    rack_geometry["fitted_transform"] = fitted
    rack.geometry_json = rack_geometry

    for shelf_index, shelf in enumerate(sorted(shelves, key=lambda item: int(item.level))):
        z_m = (
            shelf_heights[shelf_index]
            if shelf_index < len(shelf_heights)
            else float(origin.get("z_m") or 0.0)
        )
        shelf_geometry = dict(shelf.geometry_json or {})
        shelf_geometry["template"] = {
            "template_id": int(template.id),
            "template_version_id": int(version.id),
            "shelf_height_m": round(z_m, 3),
        }
        shelf.geometry_json = shelf_geometry
        rows = sorted(bins_by_shelf.get(int(shelf.id), []), key=lambda item: str(item.code))
        for bin_index, bin_row in enumerate(rows):
            offset = (bin_index + 0.5) * bin_pitch
            snapped = {
                "frame_id": "warehouse_map",
                "x_m": round(float(origin["x_m"]) + float(axis["x"]) * offset, 3),
                "y_m": round(float(origin["y_m"]) + float(axis["y"]) * offset, 3),
                "z_m": round(z_m, 3),
            }
            geometry = dict(bin_row.geometry_json or {})
            geometry["target_point"] = snapped
            geometry["template"] = {
                "template_id": int(template.id),
                "template_version_id": int(version.id),
                "template_version": int(version.version),
                "bin_index": bin_index,
                "bin_pitch_m": bin_pitch,
            }
            geometry["fitted_transform"] = fitted
            bin_row.geometry_json = geometry

    return {
        "template": template_meta,
        "fitted_transform": fitted,
        "snapped_bin_count": len(all_bins),
    }

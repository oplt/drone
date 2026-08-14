"""Warehouse structure extraction — target generation."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid
from backend.modules.warehouse.schemas import (
    WAREHOUSE_MAP_FRAME_ID,
    WarehouseLocalPoint,
    WarehouseShelfNormal,
)
from backend.modules.warehouse.service.inspection import compute_scan_pose

from .clearance import classify_clearance
from .confidence import _confidence_mean, _target_confidence_breakdown
from .models import GeneratedTarget, StructureExtractionParams, StructureResult, _Band

def _scanner_standoff_m(params: StructureExtractionParams) -> float:
    horizontal_fov_deg = 70.0
    barcode_width_m = 0.08
    roi_width_fraction = 0.50
    fov_width_m_at_1m = 2.0 * math.tan(math.radians(horizontal_fov_deg) * 0.5)
    min_barcode_fit_m = barcode_width_m / max(roi_width_fraction * fov_width_m_at_1m, 1e-6)
    downwash_standoff_m = float(params.drone_radius_m) + max(float(params.clearance_margin_m), 0.20)
    return round(max(float(params.standoff_m), min_barcode_fit_m, downwash_standoff_m), 3)

def _scanner_metadata(
    *,
    target_point: WarehouseLocalPoint,
    shelf_normal: WarehouseShelfNormal,
    standoff_m: float,
    params: StructureExtractionParams,
    template_fit: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "barcode_mode": "decode" if params.barcode_scan_expected else "decode_if_present",
        "empty_bin_vision_mode": "classify_empty_bin",
        "expected_sku": None,
        "expected_barcode": None,
        "image_roi": {
            "mode": "center_crop",
            "x": 0.25,
            "y": 0.20,
            "width": 0.50,
            "height": 0.60,
        },
        "min_confidence": 0.75,
        "scanner_fov_deg": {"horizontal": 70.0, "vertical": 45.0},
        "barcode_expected_size_m": {"width": 0.08, "height": 0.03},
        "lighting_constraints": {
            "min_lux": 100.0,
            "avoid_glare": True,
            "preferred_incidence_deg": 0.0,
            "max_incidence_deg": 25.0,
        },
        "target_point_local_json": target_point.model_dump(),
        "shelf_normal_local_json": shelf_normal.model_dump(),
        "standoff_m": float(standoff_m),
        "drone_radius_m": float(params.drone_radius_m),
        "downwash_margin_m": max(float(params.clearance_margin_m), 0.20),
        "template_fit": dict(template_fit or {}),
    }

def _angle_between_deg(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    ax, ay, az = a
    bx, by, bz = b
    denom = math.sqrt(ax * ax + ay * ay + az * az) * math.sqrt(bx * bx + by * by + bz * bz)
    if denom <= 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by + az * bz) / denom))))

def _scan_pose_validation(
    *,
    target_point: WarehouseLocalPoint,
    shelf_normal: WarehouseShelfNormal,
    scan_pose: Any,
    clearance_m: float,
    clearance_source: str,
    occupancy_grid: OccupancyGrid | None,
    params: StructureExtractionParams,
) -> tuple[dict[str, Any], str | None]:
    required_clearance_m = float(params.required_clearance_m)
    pose = LocalPose(
        x_m=float(scan_pose.x_m),
        y_m=float(scan_pose.y_m),
        z_m=float(scan_pose.z_m),
        yaw_deg=float(scan_pose.yaw_deg or 0.0),
        frame_id=str(scan_pose.frame_id),
    )
    target_vector = (
        float(target_point.x_m) - pose.x_m,
        float(target_point.y_m) - pose.y_m,
        float(target_point.z_m) - pose.z_m,
    )
    normal_vector = (float(shelf_normal.x), float(shelf_normal.y), float(shelf_normal.z))
    approach_angle_deg = _angle_between_deg(target_vector, normal_vector)
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not 0.25 <= pose.z_m <= float(params.ceiling_max_m):
        failures.append(
            {
                "check": "altitude",
                "message": "Scan pose is outside altitude envelope",
                "z_m": round(pose.z_m, 3),
            }
        )
    if approach_angle_deg > 25.0:
        failures.append(
            {
                "check": "approach_cone",
                "message": "Scan pose does not face the rack normal",
                "angle_deg": round(approach_angle_deg, 3),
            }
        )
    if clearance_m < required_clearance_m:
        failures.append(
            {
                "check": "clearance",
                "message": "Scan pose violates drone radius/downwash clearance",
                "clearance_m": round(float(clearance_m), 3),
                "required_m": round(required_clearance_m, 3),
                "source": clearance_source,
            }
        )

    path_summary: dict[str, Any] = {
        "dock_reference": "map_origin_nearest_free",
        "required_clearance_m": round(required_clearance_m, 3),
    }
    if occupancy_grid is None:
        warnings.append(
            {
                "check": "esdf_occupancy",
                "message": "No ESDF or occupancy grid was available during generation",
            }
        )
        path_summary.update({"status": "needs_review", "reason": "path_validation_requires_grid"})
    else:
        dock_pose = LocalPose(
            x_m=float(occupancy_grid.origin_x_m),
            y_m=float(occupancy_grid.origin_y_m),
            z_m=pose.z_m,
            frame_id=pose.frame_id,
        )
        outbound = occupancy_grid.astar_path(dock_pose, pose, clearance_m=required_clearance_m)
        inbound = occupancy_grid.astar_path(pose, dock_pose, clearance_m=required_clearance_m)
        if not outbound or not inbound:
            failures.append(
                {
                    "check": "swept_path",
                    "message": "No collision-free inflated round trip exists",
                    "outbound_samples": len(outbound),
                    "return_samples": len(inbound),
                }
            )
            path_summary.update({"status": "rejected", "reason": "swept_path_unreachable"})
        else:
            path_summary.update(
                {
                    "status": "active",
                    "outbound_samples": len(outbound),
                    "return_samples": len(inbound),
                    "outbound_length_m": round(occupancy_grid.path_length_m(outbound), 3),
                    "return_length_m": round(occupancy_grid.path_length_m(inbound), 3),
                }
            )
        path_summary["pose_cell"] = list(occupancy_grid.world_to_cell(pose))

    esdf_summary = {
        "status": "fallback_used" if occupancy_grid is not None else "unavailable",
        "source": "occupancy_grid" if occupancy_grid is not None else None,
    }
    validation = {
        "status": "rejected" if failures else path_summary.get("status", "active"),
        "esdf": esdf_summary,
        "scan_pose": {
            "approach_angle_deg": round(approach_angle_deg, 3),
            "clearance_m": round(float(clearance_m), 3),
            "clearance_source": clearance_source,
        },
        "path": path_summary,
        "warnings": warnings,
        "failures": failures,
    }
    reason = None
    if failures:
        reason = str(failures[0].get("check") or "scan_pose_validation_failed")
    elif path_summary.get("status") != "active":
        reason = str(path_summary.get("reason") or "path_validation_needs_review")
    return validation, reason

def _emit_bay_targets(
    *,
    result: StructureResult,
    params: StructureExtractionParams,
    bay: _Band,
    row: _Band,
    face: dict[str, Any],
    shelf_levels: list[float],
    uv_to_world,
    clearance_tree: cKDTree,
    occupancy_grid: OccupancyGrid | None,
    rack_code: str,
    face_plane: dict[str, Any] | None = None,
    template_fit: dict[str, Any] | None = None,
) -> None:
    """Stage D: divide a bay face into bins x shelf levels -> scan targets."""
    face_v = float(face["face_v"])
    sign = float(face["sign"])
    aisle_code = str(face["aisle_code"])
    nx, ny = uv_to_world(0.0, sign)  # world direction of +v*sign at origin...
    ox, oy = uv_to_world(0.0, 0.0)
    normal_x = nx - ox
    normal_y = ny - oy
    nlen = math.hypot(normal_x, normal_y)
    if nlen <= 1e-9:
        return
    normal_x /= nlen
    normal_y /= nlen

    if params.rack_template_bin_count is not None:
        n_bins = min(int(params.rack_template_bin_count), params.max_bins_per_rack_face)
    else:
        pitch = max(params.bin_pitch_m, params.min_target_spacing_m, params.grid_res_m * 2)
        n_bins = max(1, round(bay.width / pitch))
        n_bins = min(n_bins, params.max_bins_per_rack_face)
    target_standoff_m = _scanner_standoff_m(params)
    for b_idx in range(n_bins):
        u_center = bay.lo + (b_idx + 0.5) * (bay.width / n_bins)
        for level_idx, z_level in enumerate(shelf_levels):
            tx, ty = uv_to_world(u_center, face_v)
            target_point = WarehouseLocalPoint(
                frame_id=WAREHOUSE_MAP_FRAME_ID, x_m=tx, y_m=ty, z_m=float(z_level)
            )
            shelf_normal = WarehouseShelfNormal(
                frame_id=WAREHOUSE_MAP_FRAME_ID, x=normal_x, y=normal_y, z=0.0
            )
            try:
                scan_pose = compute_scan_pose(
                    target_point=target_point,
                    shelf_normal=shelf_normal,
                    standoff_m=target_standoff_m,
                )
            except ValueError:
                continue

            if occupancy_grid is not None:
                clearance = occupancy_grid.clearance_at(
                    LocalPose(
                        x_m=scan_pose.x_m,
                        y_m=scan_pose.y_m,
                        z_m=scan_pose.z_m,
                        frame_id=scan_pose.frame_id,
                    )
                )
                clearance_source = "occupancy_grid"
            else:
                clearance, _ = clearance_tree.query(
                    np.array([scan_pose.x_m, scan_pose.y_m, scan_pose.z_m], dtype=np.float64)
                )
                clearance_source = "point_cloud_kdtree"
            clearance = float(clearance)
            clearance_status = classify_clearance(
                clearance,
                strict_clearance_m=params.required_clearance_m,
                review_clearance_m=params.review_clearance_m,
                reliable_evidence=occupancy_grid is not None,
            )
            scanner_metadata = _scanner_metadata(
                target_point=target_point,
                shelf_normal=shelf_normal,
                standoff_m=target_standoff_m,
                params=params,
                template_fit=template_fit,
            )
            path_validation, failure_reason = _scan_pose_validation(
                target_point=target_point,
                shelf_normal=shelf_normal,
                scan_pose=scan_pose,
                clearance_m=clearance,
                clearance_source=clearance_source,
                occupancy_grid=occupancy_grid,
                params=params,
            )
            if path_validation.get("status") == "rejected" and clearance_status != "rejected":
                clearance_status = "rejected"
            elif path_validation.get("status") != "active" and clearance_status == "active":
                clearance_status = "needs_review"
            if clearance_status != "active" and failure_reason is None:
                failure_reason = (
                    "clearance_below_required"
                    if clearance_status == "rejected"
                    else "clearance_requires_review"
                )
            confidence_breakdown = _target_confidence_breakdown(
                clearance_status=clearance_status,
                clearance_source=clearance_source,
                face_plane=face_plane,
                template_fit=template_fit,
            )
            confidence = _confidence_mean(list(confidence_breakdown.values()))
            if clearance_status == "rejected":
                result.rejected_clearance += 1
                half = max(params.grid_res_m, 0.05) * 0.5
                rejection_reason = failure_reason or "clearance_below_required"
                result.rejection_diagnostics.append(
                    {
                        "candidate_id": f"{rack_code}:{aisle_code}:B{b_idx + 1}:L{level_idx}",
                        "rejection_reason": rejection_reason,
                        "clearance_m": round(clearance, 3),
                        "required_clearance_m": round(params.required_clearance_m, 3),
                        "path_status": path_validation.get("status"),
                        "bbox": [
                            round(scan_pose.x_m - half, 3),
                            round(scan_pose.y_m - half, 3),
                            round(scan_pose.z_m - half, 3),
                            round(scan_pose.x_m + half, 3),
                            round(scan_pose.y_m + half, 3),
                            round(scan_pose.z_m + half, 3),
                        ],
                        "frame_id": WAREHOUSE_MAP_FRAME_ID,
                    }
                )
            result.targets.append(
                GeneratedTarget(
                    aisle_code=aisle_code,
                    rack_code=rack_code,
                    shelf_level=level_idx,
                    bin_code=f"B{b_idx + 1}",
                    target_point=target_point.model_dump(),
                    shelf_normal=shelf_normal.model_dump(),
                    scan_pose=scan_pose.model_dump(),
                    standoff_m=float(target_standoff_m),
                    priority=100,
                    clearance_status=clearance_status,
                    clearance_m=clearance,
                    clearance_source=clearance_source,
                    confidence=confidence,
                    confidence_breakdown=confidence_breakdown,
                    template_metadata={
                        "template_version_id": params.rack_template_version_id,
                        "template_fit": dict(template_fit or {}),
                        "rack_face_plane": dict(face_plane or {}),
                        "rack_template_bin_count": params.rack_template_bin_count,
                        "rack_template_bay_width_m": params.rack_template_bay_width_m,
                        "rack_template_shelf_levels_m": list(
                            params.rack_template_shelf_levels_m
                        ),
                    },
                    scanner_metadata=scanner_metadata,
                    path_validation=path_validation,
                    failure_reason=failure_reason,
                )
            )

def _target_summary(target: GeneratedTarget) -> dict[str, Any]:
    return {
        "candidate_id": (
            f"{target.rack_code}:{target.aisle_code}:{target.bin_code}:L{target.shelf_level}"
        ),
        "aisle_code": target.aisle_code,
        "rack_code": target.rack_code,
        "shelf_level": target.shelf_level,
        "bin_code": target.bin_code,
        "status": target.clearance_status,
        "clearance_m": (round(target.clearance_m, 3) if target.clearance_m is not None else None),
        "clearance_source": target.clearance_source,
        "confidence": round(float(target.confidence), 3),
        "confidence_breakdown": dict(target.confidence_breakdown),
        "template": dict(target.template_metadata or {}),
        "scanner_metadata": dict(target.scanner_metadata or {}),
        "path_validation": dict(target.path_validation or {}),
        "failure_reason": target.failure_reason,
        "target_point": dict(target.target_point),
        "scan_pose": dict(target.scan_pose),
    }

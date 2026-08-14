"""Warehouse structure extraction — pipeline."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from backend.modules.warehouse.planning.indoor.models import OccupancyGrid
from backend.modules.warehouse.schemas import WAREHOUSE_MAP_FRAME_ID
from backend.modules.warehouse.service.coordinate_frames import transform_odom_points

from . import deps
from .aisle_detection import (
    _aisle_confidence_breakdown,
    _aisle_faces_for_row,
    _aisle_graph_summary,
    _occupancy_aisle_graph_summary,
)
from .confidence import _confidence_mean, _rack_confidence_breakdown
from .geometry import _rotation
from .models import StructureExtractionError, StructureExtractionParams, StructureResult, _Band
from .preprocessing import load_flight_cloud
from .rack_detection import (
    _plane_for_face,
    _rack_face_plane_summary,
    _template_bays,
    _template_fit_metrics,
    _upright_bays,
)
from .shelf_detection import _shelf_confidence_breakdown
from .routing import _assign_astar_priority, _assign_serpentine_priority
from .summary import _params_to_dict
from .target_generation import _target_summary

logger = logging.getLogger(__name__)

def extract_structure(
    cloud_xyz: np.ndarray,
    *,
    params: StructureExtractionParams,
    occupancy_grid: OccupancyGrid | None = None,
) -> StructureResult:
    """Run stages A-D on a merged cloud and return targets + summary."""
    params = params.sanitized()
    if cloud_xyz.shape[0] < 50:
        raise StructureExtractionError("Cloud too small for structure extraction.")

    z = cloud_xyz[:, 2]
    floor_z = deps.resolve("_detect_floor_z")(z, params.grid_res_m)
    band_lo = floor_z + params.floor_margin_m
    band_hi = floor_z + params.ceiling_max_m
    band_hi = min(band_hi, float(np.percentile(z, 99.0)))
    if band_hi <= band_lo:
        band_hi = band_lo + max(params.shelf_min_spacing_m, 0.5)

    keep = (z >= band_lo) & (z <= band_hi)
    rack_mass = cloud_xyz[keep]
    if rack_mass.shape[0] < 50:
        raise StructureExtractionError(
            "No vertical structure remained after floor/ceiling removal."
        )

    xy = rack_mass[:, :2].astype(np.float64)
    if params.axis_deg is not None:
        theta = math.radians(float(params.axis_deg))
    else:
        theta = deps.resolve("_dominant_axis_rad")(xy)
    rot = _rotation(theta)
    uv = xy @ rot.T  # columns: u (along aisle), v (cross aisle)
    u_all = uv[:, 0]
    v_all = uv[:, 1]

    # Primary core: vertical rack face planes clustered into rack rows. The
    # density-band extractor remains as a review-only fallback for weak scans.
    rack_rows, plane_clusters, used_density_fallback = deps.resolve("_extract_vertical_plane_rows")(
        u_all=u_all,
        v_all=v_all,
        z_all=rack_mass[:, 2],
        params=params,
    )
    if not rack_rows:
        raise StructureExtractionError("No rack face planes or fallback rack rows detected.")

    aisles = deps.resolve("_density_bands")(
        v_all,
        res=params.grid_res_m,
        occupied=False,
        min_width=params.min_aisle_width_m,
        occ_threshold=0.18,
    )

    inv_rot = rot.T  # maps (u, v) back to world XY

    def _uv_to_world(u: float, v: float) -> tuple[float, float]:
        world = inv_rot @ np.array([u, v], dtype=np.float64)
        return float(world[0]), float(world[1])

    # KD-tree over the rack mass for the clearance gate (XY+Z).
    clearance_tree = cKDTree(rack_mass.astype(np.float64))

    result = StructureResult(point_count=int(cloud_xyz.shape[0]))
    aisle_summaries: list[dict[str, Any]] = []
    rack_summaries: list[dict[str, Any]] = []

    # Aisle centerlines (summary + code lookup).
    aisle_centers: list[float] = [a.center for a in aisles]
    for a_idx, aisle in enumerate(aisles):
        x0, y0 = _uv_to_world(float(u_all.min()), aisle.center)
        x1, y1 = _uv_to_world(float(u_all.max()), aisle.center)
        aisle_summaries.append(
            {
                "code": f"A{a_idx + 1}",
                "centerline_world": [x0, y0, x1, y1],
                "width_m": round(aisle.width, 3),
                "z_min": round(band_lo, 3),
                "z_max": round(band_hi, 3),
                "confidence_breakdown": _aisle_confidence_breakdown(
                    aisle=aisle,
                    min_aisle_width_m=params.min_aisle_width_m,
                ),
            }
        )

    rack_index = 0
    for row in rack_rows:
        in_row = (v_all >= row.lo) & (v_all <= row.hi)
        if int(in_row.sum()) < 30:
            continue
        u_row = u_all[in_row]
        z_row = rack_mass[in_row, 2]

        # Stage C: split the rack row into bays along the aisle axis.
        bay_source = "density_fallback"
        if params.rack_template_bay_width_m is not None:
            bays = _template_bays(
                u_min=float(u_row.min()),
                u_max=float(u_row.max()),
                bay_width_m=float(params.rack_template_bay_width_m),
                min_rack_length_m=float(params.min_rack_length_m),
            )
            bay_source = "template"
        else:
            bays = _upright_bays(u_row=u_row, z_row=z_row, params=params)
            if bays:
                bay_source = "upright_pitch"
            if not bays:
                bays = deps.resolve("_density_bands")(
                    u_row,
                    res=params.grid_res_m,
                    occupied=True,
                    min_width=params.min_rack_length_m,
                    occ_threshold=0.12,
                )
                bay_source = "density_fallback"
        if not bays:
            bays = [_Band(lo=float(u_row.min()), hi=float(u_row.max()))]
            bay_source = "whole_row_fallback"

        # Which aisle(s) border this rack row -> face normals point into them.
        faces = _aisle_faces_for_row(row, aisle_centers)
        if not faces:
            continue

        for bay in bays:
            rack_index += 1
            rack_code = f"R{rack_index}"
            in_bay = (u_row >= bay.lo) & (u_row <= bay.hi)
            z_bay = z_row[in_bay]
            if z_bay.size < 20:
                continue

            shelf_levels = (
                list(params.rack_template_shelf_levels_m)
                if params.rack_template_shelf_levels_m
                else deps.resolve("_detect_shelf_levels")(
                    z_bay,
                    spacing=params.shelf_min_spacing_m,
                    res=params.grid_res_m,
                    max_levels=params.max_shelf_levels,
                )
            )
            if not shelf_levels:
                shelf_levels = [float(np.median(z_bay))]
            shelf_confidence = _shelf_confidence_breakdown(
                levels=shelf_levels,
                z_points=z_bay,
                params=params,
            )

            # Rack bbox (world) for the summary / overlays.
            cx, cy = _uv_to_world(bay.center, row.center)
            template_fit = _template_fit_metrics(
                bay=bay,
                shelf_levels=shelf_levels,
                params=params,
            )
            face_planes = []
            for face in faces:
                plane_cluster = _plane_for_face(face, plane_clusters)
                face_planes.append(
                    _rack_face_plane_summary(
                        u_row=u_row,
                        v_row=v_all[in_row],
                        z_row=z_row,
                        bay=bay,
                        face=face,
                        uv_to_world=_uv_to_world,
                        plane_cluster=plane_cluster,
                        fallback=used_density_fallback,
                    )
                )
            rack_summaries.append(
                {
                    "code": rack_code,
                    "row_v": round(row.center, 3),
                    "center_world": [round(cx, 3), round(cy, 3), round(float(np.median(z_bay)), 3)],
                    "length_m": round(bay.width, 3),
                    "depth_m": round(row.width, 3),
                    "z_min": round(float(z_bay.min()), 3),
                    "z_max": round(float(z_bay.max()), 3),
                    "faces": [f["aisle_code"] for f in faces],
                    "face_planes": face_planes,
                    "bay_detection": bay_source,
                    "shelf_detection": {
                        "source": (
                            "rack_template"
                            if params.rack_template_shelf_levels_m
                            else "horizontal_plane_histogram"
                        ),
                        "levels_m": [round(float(level), 3) for level in shelf_levels],
                        "confidence_breakdown": shelf_confidence,
                    },
                    "template_fit": template_fit,
                    "confidence_breakdown": _rack_confidence_breakdown(
                        points=int(z_bay.size),
                        face_planes=face_planes,
                        template_fit=template_fit,
                        shelf_confidence=shelf_confidence,
                        fallback=used_density_fallback,
                    ),
                }
            )

            for face in faces:
                deps.resolve("_emit_bay_targets")(
                    result=result,
                    params=params,
                    bay=bay,
                    row=row,
                    face=face,
                    shelf_levels=shelf_levels,
                    uv_to_world=_uv_to_world,
                    clearance_tree=clearance_tree,
                    occupancy_grid=occupancy_grid,
                    rack_code=rack_code,
                    face_plane=next(
                        (
                            plane
                            for plane in face_planes
                            if plane.get("aisle_code") == face.get("aisle_code")
                        ),
                        None,
                    ),
                    template_fit=template_fit,
                )

    if not result.targets and not rack_summaries:
        raise StructureExtractionError("No usable rack structure was detected.")

    if occupancy_grid is not None:
        _assign_astar_priority(
            result.targets,
            occupancy_grid=occupancy_grid,
            clearance_m=params.required_clearance_m,
        )
    else:
        _assign_serpentine_priority(result.targets)

    if used_density_fallback:
        for target in result.targets:
            if target.clearance_status == "active":
                target.clearance_status = "needs_review"
            target.confidence_breakdown["fallback_extractor"] = 0.25
            target.confidence = _confidence_mean(list(target.confidence_breakdown.values()))

    target_counts = {
        "candidate": len(result.targets),
        "active": sum(target.clearance_status == "active" for target in result.targets),
        "needs_review": sum(target.clearance_status == "needs_review" for target in result.targets),
        "rejected": sum(target.clearance_status == "rejected" for target in result.targets),
    }
    occupancy_graph = _occupancy_aisle_graph_summary(occupancy_grid, z_m=band_lo)
    density_graph = _aisle_graph_summary(
        aisles,
        u_min=float(u_all.min()),
        u_max=float(u_all.max()),
        min_aisle_width_m=params.min_aisle_width_m,
    )
    result.summary = {
        "status": "ready" if target_counts["active"] > 0 else "degraded",
        "coordinate_setup_status": ("active" if target_counts["active"] > 0 else "draft"),
        "manual_review_required": target_counts["needs_review"] > 0 or target_counts["active"] == 0,
        "frame_id": WAREHOUSE_MAP_FRAME_ID,
        "floor_z": round(floor_z, 3),
        "axis_deg": round(math.degrees(theta), 2),
        "height_band_m": [round(band_lo, 3), round(band_hi, 3)],
        "algorithm_core": {
            "primary": "vertical_plane_graph",
            "fallback_used": bool(used_density_fallback),
            "plane_cluster_count": len(plane_clusters),
            "row_source": "density_fallback" if used_density_fallback else "parallel_face_planes",
        },
        "rack_plane_clusters": [
            {
                "v_m": round(plane.v, 3),
                "u_range_m": [round(plane.u_lo, 3), round(plane.u_hi, 3)],
                "z_range_m": [round(plane.z_lo, 3), round(plane.z_hi, 3)],
                "support_points": plane.support_points,
                "residual_m": round(plane.residual_m, 4),
                "source": plane.source,
            }
            for plane in plane_clusters
        ],
        "aisles": aisle_summaries,
        "aisle_graph": occupancy_graph or density_graph,
        "racks": rack_summaries,
        "counts": {
            "aisles": len(aisle_summaries),
            "racks": len(rack_summaries),
            "targets": len(result.targets),
            "active_targets": target_counts["active"],
            "review_targets": target_counts["needs_review"],
            "candidate_targets": target_counts["candidate"],
            "rejected_clearance": result.rejected_clearance,
        },
        "target_counts": target_counts,
        "candidate_targets": [_target_summary(target) for target in result.targets],
        "active_targets": [
            _target_summary(target)
            for target in result.targets
            if target.clearance_status == "active"
        ],
        "review_targets": [
            _target_summary(target)
            for target in result.targets
            if target.clearance_status == "needs_review"
        ],
        "rejected_targets": [
            _target_summary(target)
            for target in result.targets
            if target.clearance_status == "rejected"
        ],
        "params": _params_to_dict(params),
        "clearance": {
            "source": "occupancy_grid" if occupancy_grid is not None else "point_cloud_kdtree",
            "required_clearance_m": round(params.required_clearance_m, 3),
        },
        "warnings": (
            (
                ["Structure detected but all scan targets failed the clearance gate."]
                if target_counts["active"] == 0
                else []
            )
            + (
                ["Plane evidence was weak; PCA/density fallback outputs require review."]
                if used_density_fallback and result.targets
                else []
            )
        ),
        "rejection_diagnostics": result.rejection_diagnostics,
        "routing": {
            "mode": "occupancy_astar" if occupancy_grid is not None else "aisle_serpentine",
            "source": (
                "persisted_occupancy_grid" if occupancy_grid is not None else "geometry_ordering"
            ),
        },
    }
    return result


def extract_structure_from_flight(
    client_flight_id: str,
    *,
    params: StructureExtractionParams,
    occupancy_grid: OccupancyGrid | None = None,
    odom_to_warehouse_map_transform: dict[str, Any] | None = None,
) -> StructureResult:
    """Convenience entry point: load the flight cloud then run extraction."""
    params = params.sanitized()
    cloud = load_flight_cloud(client_flight_id, params=params)
    if odom_to_warehouse_map_transform is None:
        raise StructureExtractionError("Locked warehouse_map -> odom localization is required")
    cloud = transform_odom_points(cloud, odom_to_warehouse_map_transform).astype(np.float32)
    # OccupancyGrid currently has axis-aligned origin only (no origin yaw). It
    # cannot be safely carried across an arbitrary localization rotation. Use
    # transformed point-cloud clearance until the grid contract supports SE(2).
    occupancy_grid = None
    logger.info(
        "structure_extraction loaded flight=%s points=%s voxel=%.3f occupancy=%s",
        client_flight_id,
        cloud.shape[0],
        params.voxel_m,
        occupancy_grid is not None,
    )
    result = extract_structure(cloud, params=params, occupancy_grid=occupancy_grid)
    result.summary["source_frame_id"] = "odom"
    result.summary["localization_applied"] = True
    clearance = result.summary.get("clearance")
    if isinstance(clearance, dict):
        if occupancy_grid is not None:
            clearance["source"] = "occupancy_grid"
        else:
            try:
                from backend.modules.warehouse.service.live_map_manifest import load_flight_manifest

                manifest = load_flight_manifest(client_flight_id)
                if manifest is not None and not manifest.nvblox_available:
                    clearance["source"] = "point_cloud_fallback"
                    clearance["missing_topics"] = list(manifest.missing_topics or [])
            except Exception:
                logger.debug("structure_extraction_clearance_hints_failed", exc_info=True)
    return result

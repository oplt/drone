"""Warehouse structure extraction — aisle detection."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid
from backend.modules.warehouse.schemas import (
    WAREHOUSE_MAP_FRAME_ID,
    WarehouseLocalPoint,
    WarehouseShelfNormal,
)
from backend.modules.warehouse.service.coordinate_frames import transform_odom_points
from backend.modules.warehouse.service.inspection import compute_scan_pose
from backend.modules.warehouse.service.live_map_storage import warehouse_live_map_chunk_storage
from backend.modules.warehouse.service.occupancy_grid_parser import decode_occupancy_grid

logger = logging.getLogger(__name__)

from .models import _Band

def _occupancy_aisle_graph_summary(
    occupancy_grid: OccupancyGrid | None,
    *,
    z_m: float,
) -> dict[str, Any] | None:
    if occupancy_grid is None or occupancy_grid.width <= 0 or occupancy_grid.height <= 0:
        return None
    free_cells: list[tuple[int, int]] = []
    for cell in occupancy_grid.iter_cells():
        if str(cell.state).split(".")[-1].lower() == "free":
            free_cells.append((int(cell.x_idx), int(cell.y_idx)))
    if not free_cells:
        return None
    by_y: dict[int, list[int]] = {}
    for x_idx, y_idx in free_cells:
        by_y.setdefault(y_idx, []).append(x_idx)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    aisle_idx = 0
    for y_idx, xs in sorted(by_y.items()):
        xs = sorted(xs)
        runs: list[tuple[int, int]] = []
        start = prev = xs[0]
        for x_idx in xs[1:]:
            if x_idx == prev + 1:
                prev = x_idx
                continue
            runs.append((start, prev))
            start = prev = x_idx
        runs.append((start, prev))
        for start, end in runs:
            if end - start < 2:
                continue
            aisle_idx += 1
            start_pose = occupancy_grid.cell_to_pose(
                start,
                y_idx,
                z_m=z_m,
                frame_id=WAREHOUSE_MAP_FRAME_ID,
            )
            end_pose = occupancy_grid.cell_to_pose(
                end,
                y_idx,
                z_m=z_m,
                frame_id=WAREHOUSE_MAP_FRAME_ID,
            )
            start_id = f"OG{aisle_idx}:start"
            end_id = f"OG{aisle_idx}:end"
            nodes.extend(
                [
                    {
                        "id": start_id,
                        "x_m": round(start_pose.x_m, 3),
                        "y_m": round(start_pose.y_m, 3),
                    },
                    {
                        "id": end_id,
                        "x_m": round(end_pose.x_m, 3),
                        "y_m": round(end_pose.y_m, 3),
                    },
                ]
            )
            edges.append(
                {
                    "from": start_id,
                    "to": end_id,
                    "length_m": round(start_pose.planar_distance_to(end_pose), 3),
                    "source": "occupancy_free_space",
                    "confidence": 1.0,
                }
            )
    if not edges:
        return None
    return {"source": "occupancy_free_space", "nodes": nodes, "edges": edges}

def _aisle_faces_for_row(
    row: _Band,
    aisle_centers: list[float],
) -> list[dict[str, Any]]:
    """Return the rack face(s): each adjacent aisle gives a face plane + normal.

    ``face_v`` is the rack edge facing the aisle; ``sign`` is the v-direction the
    drone approaches from (toward the aisle).
    """
    faces: list[dict[str, Any]] = []
    for a_idx, center in enumerate(aisle_centers):
        code = f"A{a_idx + 1}"
        if center > row.hi:
            # Aisle on the +v side; rack face is row.hi, normal points +v.
            faces.append(
                {"face_v": row.hi, "sign": 1.0, "aisle_code": code, "gap": center - row.hi}
            )
        elif center < row.lo:
            faces.append(
                {"face_v": row.lo, "sign": -1.0, "aisle_code": code, "gap": row.lo - center}
            )
    # Keep only the nearest aisle on each side to avoid duplicate faces.
    nearest: dict[float, dict[str, Any]] = {}
    for face in faces:
        key = face["sign"]
        if key not in nearest or face["gap"] < nearest[key]["gap"]:
            nearest[key] = face
    return list(nearest.values())

def _aisle_graph_summary(
    aisles: list[_Band],
    *,
    u_min: float,
    u_max: float,
    min_aisle_width_m: float,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    length = max(0.0, float(u_max) - float(u_min))
    for index, aisle in enumerate(aisles, start=1):
        start_id = f"A{index}:start"
        end_id = f"A{index}:end"
        nodes.extend(
            [
                {
                    "id": start_id,
                    "aisle_code": f"A{index}",
                    "u_m": round(u_min, 3),
                    "v_m": round(aisle.center, 3),
                },
                {
                    "id": end_id,
                    "aisle_code": f"A{index}",
                    "u_m": round(u_max, 3),
                    "v_m": round(aisle.center, 3),
                },
            ]
        )
        edges.append(
            {
                "from": start_id,
                "to": end_id,
                "length_m": round(length, 3),
                "width_m": round(aisle.width, 3),
                "source": "density_free_space",
                "confidence": _aisle_confidence_breakdown(
                    aisle=aisle,
                    min_aisle_width_m=min_aisle_width_m,
                )["geometry"],
            }
        )
    return {"source": "density_free_space", "nodes": nodes, "edges": edges}

def _aisle_confidence_breakdown(*, aisle: _Band, min_aisle_width_m: float) -> dict[str, float]:
    width_ratio = float(aisle.width) / max(float(min_aisle_width_m), 1e-6)
    width_score = max(0.0, min(1.0, width_ratio))
    return {
        "width": round(width_score, 3),
        "geometry": round(width_score, 3),
    }

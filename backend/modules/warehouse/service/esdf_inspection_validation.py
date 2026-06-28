from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid


def esdf_points_from_structure_readiness(readiness: object) -> np.ndarray | None:
    """Parse XYZ samples from a structure-input ESDF PointCloud2 YAML echo."""
    text = getattr(readiness, "esdf_message_text", None)
    if not text:
        return None
    try:
        import yaml

        from backend.modules.warehouse.service.pointcloud2_parser import parse_pointcloud2_yaml

        payload = yaml.safe_load(text)
        if not isinstance(payload, dict):
            return None
        parsed = parse_pointcloud2_yaml(payload, max_points=2000, downsample=True)
        if parsed is None or parsed.xyz.size < 3:
            return None
        return np.asarray(parsed.xyz, dtype=np.float32).reshape((-1, 3))
    except Exception:
        return None


@dataclass(frozen=True)
class EsdfValidationPolicy:
    min_clearance_m: float = 0.35
    inflation_m: float = 0.15


def _distance_at_pose(esdf_points: np.ndarray, pose: LocalPose) -> float | None:
    if esdf_points.size < 3:
        return None
    points = np.asarray(esdf_points, dtype=np.float32).reshape((-1, 3))
    if points.shape[0] == 0:
        return None
    deltas = points - np.asarray([pose.x_m, pose.y_m, pose.z_m], dtype=np.float32)
    return float(np.min(np.linalg.norm(deltas, axis=1)))


def validate_inspection_path_esdf(
    *,
    poses: list[LocalPose],
    esdf_points_xyz: np.ndarray | None,
    grid: OccupancyGrid | None = None,
    grid_poses: list[LocalPose] | None = None,
    policy: EsdfValidationPolicy = EsdfValidationPolicy(),
) -> dict[str, Any]:
    """Augment inspection validation with ESDF clearance sampling.

    When an ESDF point cloud is unavailable, occupancy-grid inflated clearance is used
    as a fallback so preview validation still runs.
    """
    warnings: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    required_clearance = float(policy.min_clearance_m) + float(policy.inflation_m)

    if esdf_points_xyz is not None and np.asarray(esdf_points_xyz).size >= 3:
        for index, pose in enumerate(poses):
            distance_m = _distance_at_pose(np.asarray(esdf_points_xyz), pose)
            samples.append({"index": index, "distance_m": distance_m})
            if distance_m is None:
                warnings.append(
                    {
                        "check": "esdf_sample",
                        "message": "ESDF distance unavailable for pose",
                        "index": index,
                    }
                )
                continue
            if distance_m < required_clearance:
                failures.append(
                    {
                        "check": "esdf_clearance",
                        "message": "Pose violates ESDF inflated clearance",
                        "index": index,
                        "distance_m": distance_m,
                        "required_m": required_clearance,
                    }
                )
    elif grid is not None and grid_poses is not None:
        for index, grid_pose in enumerate(grid_poses):
            cell = grid.world_to_cell(grid_pose)
            if not grid.is_traversable(*cell, clearance_m=required_clearance):
                failures.append(
                    {
                        "check": "occupancy_esdf_fallback",
                        "message": "Pose lacks inflated occupancy clearance (ESDF unavailable)",
                        "index": index,
                    }
                )
        warnings.append(
            {
                "check": "esdf_unavailable",
                "message": "ESDF point cloud unavailable; used occupancy-grid inflated clearance",
            }
        )
    else:
        warnings.append(
            {
                "check": "esdf_unavailable",
                "message": "No ESDF or occupancy evidence for clearance validation",
            }
        )

    return {
        "passed": not failures,
        "required_clearance_m": required_clearance,
        "samples": samples,
        "warnings": warnings,
        "failures": failures,
    }


def parse_esdf_points_from_live_map_chunk(payload: dict[str, object] | None) -> np.ndarray | None:
    if not isinstance(payload, dict):
        return None
    preview = payload.get("preview_points_m")
    if isinstance(preview, list) and preview:
        try:
            return np.asarray(preview, dtype=np.float32).reshape((-1, 3))
        except (TypeError, ValueError):
            return None
    return None

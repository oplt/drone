from __future__ import annotations

import random
from typing import Any

import numpy as np


def fit_floor_plane_ransac(
    points_xyz: np.ndarray,
    *,
    distance_threshold_m: float = 0.05,
    max_iterations: int = 200,
    min_inlier_ratio: float = 0.6,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Estimate a dominant floor plane using RANSAC on XYZ points."""
    rng = rng or random.Random(0)
    arr = np.asarray(points_xyz, dtype=np.float64).reshape((-1, 3))
    finite = np.isfinite(arr).all(axis=1)
    arr = arr[finite]
    if arr.shape[0] < 3:
        return {
            "ok": False,
            "reason": "insufficient_points",
            "point_count": int(arr.shape[0]),
        }

    best_inliers: np.ndarray | None = None
    best_model: tuple[float, float, float, float] | None = None
    for _ in range(max(1, int(max_iterations))):
        sample_idx = rng.sample(range(arr.shape[0]), 3)
        p0, p1, p2 = arr[sample_idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-9:
            continue
        normal /= norm
        d = -float(np.dot(normal, p0))
        distances = np.abs(arr @ normal + d)
        inliers = distances <= float(distance_threshold_m)
        if best_inliers is None or int(inliers.sum()) > int(best_inliers.sum()):
            best_inliers = inliers
            best_model = (float(normal[0]), float(normal[1]), float(normal[2]), d)

    if best_inliers is None or best_model is None:
        return {"ok": False, "reason": "ransac_failed", "point_count": int(arr.shape[0])}

    inlier_count = int(best_inliers.sum())
    inlier_ratio = inlier_count / float(arr.shape[0])
    inlier_points = arr[best_inliers]
    residual_rms_m = float(
        np.sqrt(np.mean((inlier_points @ np.asarray(best_model[:3]) + best_model[3]) ** 2))
    )
    centroid = inlier_points.mean(axis=0)
    # Dominant horizontal axis from inlier XY covariance
    xy = inlier_points[:, :2] - centroid[:2]
    if xy.shape[0] >= 2:
        cov = np.cov(xy.T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        axis = eigvecs[:, int(np.argmax(eigvals))]
        dominant_yaw_rad = float(np.arctan2(axis[1], axis[0]))
    else:
        dominant_yaw_rad = 0.0

    return {
        "ok": inlier_ratio >= float(min_inlier_ratio),
        "point_count": int(arr.shape[0]),
        "inlier_count": inlier_count,
        "inlier_ratio": inlier_ratio,
        "residual_rms_m": residual_rms_m,
        "plane_normal": list(best_model[:3]),
        "plane_offset_m": best_model[3],
        "centroid_m": [float(centroid[0]), float(centroid[1]), float(centroid[2])],
        "dominant_yaw_rad": dominant_yaw_rad,
        "distance_threshold_m": float(distance_threshold_m),
    }

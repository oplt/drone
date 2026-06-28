from __future__ import annotations

import math
from typing import Any


def estimate_scan_odom_to_warehouse_map(
    *,
    floor_plane: dict[str, Any],
    origin_warehouse_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    yaw_flip_rad: float = 0.0,
) -> dict[str, Any]:
    """Estimate scan_odom -> warehouse_map from floor-plane RANSAC output."""
    if not floor_plane.get("ok"):
        return {"ok": False, "reason": "floor_plane_unusable"}
    centroid = floor_plane.get("centroid_m") or [0.0, 0.0, 0.0]
    yaw = float(floor_plane.get("dominant_yaw_rad") or 0.0) + float(yaw_flip_rad)
    cx, cy, cz = (float(centroid[0]), float(centroid[1]), float(centroid[2]))
    ox, oy, oz = origin_warehouse_m
    half_yaw = yaw / 2.0
    return {
        "ok": True,
        "parent_frame": "warehouse_map",
        "child_frame": "scan_odom",
        "translation": {
            "x": ox - cx,
            "y": oy - cy,
            "z": oz - cz,
        },
        "rotation": {
            "x": 0.0,
            "y": 0.0,
            "z": math.sin(half_yaw),
            "w": math.cos(half_yaw),
        },
        "dominant_yaw_rad": yaw,
        "residual_rms_m": floor_plane.get("residual_rms_m"),
        "inlier_ratio": floor_plane.get("inlier_ratio"),
    }

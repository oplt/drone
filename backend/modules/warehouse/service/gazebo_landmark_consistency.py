from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LandmarkSpec:
    name: str
    warehouse_x_m: float
    warehouse_y_m: float
    warehouse_z_m: float = 0.0


@dataclass(frozen=True)
class LandmarkObservation:
    name: str
    x_m: float
    y_m: float
    z_m: float = 0.0


def rotate_xy(x: float, y: float, yaw_rad: float) -> tuple[float, float]:
    c = math.cos(yaw_rad)
    s = math.sin(yaw_rad)
    return x * c - y * s, x * s + y * c


def transform_landmark_to_warehouse(
    observation: LandmarkObservation,
    *,
    map_to_odom: dict[str, Any],
) -> tuple[float, float, float]:
    translation = map_to_odom.get("translation") or {}
    rotation = map_to_odom.get("rotation") or {}
    tx = float(translation.get("x") or 0.0)
    ty = float(translation.get("y") or 0.0)
    tz = float(translation.get("z") or 0.0)
    qx = float(rotation.get("x") or 0.0)
    qy = float(rotation.get("y") or 0.0)
    qz = float(rotation.get("z") or 0.0)
    qw = float(rotation.get("w") or 1.0)
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    wx, wy = rotate_xy(observation.x_m, observation.y_m, yaw)
    return tx + wx, ty + wy, tz + float(observation.z_m)


def evaluate_landmark_consistency(
    *,
    landmarks: list[LandmarkSpec],
    observations: list[LandmarkObservation],
    map_to_odom: dict[str, Any],
    tolerance_m: float = 0.25,
) -> dict[str, Any]:
    expected = {item.name: item for item in landmarks}
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for observation in observations:
        spec = expected.get(observation.name)
        if spec is None:
            failures.append(f"unknown landmark {observation.name}")
            continue
        wx, wy, wz = transform_landmark_to_warehouse(observation, map_to_odom=map_to_odom)
        error_m = math.dist(
            (wx, wy, wz),
            (spec.warehouse_x_m, spec.warehouse_y_m, spec.warehouse_z_m),
        )
        ok = error_m <= float(tolerance_m)
        rows.append(
            {
                "name": observation.name,
                "observed_m": [observation.x_m, observation.y_m, observation.z_m],
                "warehouse_m": [wx, wy, wz],
                "expected_m": [spec.warehouse_x_m, spec.warehouse_y_m, spec.warehouse_z_m],
                "error_m": error_m,
                "ok": ok,
            }
        )
        if not ok:
            failures.append(f"{observation.name} error {error_m:.3f}m > {tolerance_m:.3f}m")
    missing = sorted(set(expected) - {row.name for row in observations})
    for name in missing:
        failures.append(f"missing landmark {name}")
    return {
        "passed": not failures,
        "tolerance_m": float(tolerance_m),
        "landmarks": rows,
        "failures": failures,
    }

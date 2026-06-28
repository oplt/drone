from __future__ import annotations

import math
from typing import Any

from backend.modules.vehicle_runtime.types import EnuCoordinate, LocalCoordinate


def normalize_angle_rad(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("angle must be finite radians")
    return (value + math.pi) % (2 * math.pi) - math.pi


def enu_yaw_to_ned(yaw_rad: float) -> float:
    """ENU CCW from +X to NED clockwise from north."""
    return normalize_angle_rad((math.pi / 2) - float(yaw_rad))


def ned_yaw_to_enu(yaw_rad: float) -> float:
    return normalize_angle_rad((math.pi / 2) - float(yaw_rad))


def enu_to_local_ned(coord: EnuCoordinate) -> LocalCoordinate:
    if coord.frame_id != "odom":
        raise ValueError("MAVLink local conversion requires frame_id='odom'")
    if not all(math.isfinite(float(value)) for value in (coord.x_m, coord.y_m, coord.z_m)):
        raise ValueError("ENU position must contain finite metres")
    return LocalCoordinate(
        north_m=float(coord.y_m),
        east_m=float(coord.x_m),
        down_m=-float(coord.z_m),
        yaw_rad=enu_yaw_to_ned(coord.yaw_rad) if coord.yaw_rad is not None else None,
    )


def local_ned_to_enu(coord: LocalCoordinate) -> EnuCoordinate:
    return EnuCoordinate(
        x_m=float(coord.east_m),
        y_m=float(coord.north_m),
        z_m=-float(coord.down_m),
        yaw_rad=ned_yaw_to_enu(coord.yaw_rad) if coord.yaw_rad is not None else None,
    )


def local_ned_position_to_enu(*, north_m: float, east_m: float, down_m: float) -> EnuCoordinate:
    return local_ned_to_enu(
        LocalCoordinate(
            north_m=float(north_m),
            east_m=float(east_m),
            down_m=float(down_m),
        )
    )


def _rotate(vector: tuple[float, float, float], q: dict[str, float]) -> tuple[float, float, float]:
    x, y, z = vector
    qx, qy, qz, qw = (float(q[key]) for key in ("x", "y", "z", "w"))
    # Quaternion rotation expanded to avoid a numerical dependency in vehicle infrastructure.
    return (
        (1 - 2 * (qy * qy + qz * qz)) * x
        + 2 * (qx * qy - qz * qw) * y
        + 2 * (qx * qz + qy * qw) * z,
        2 * (qx * qy + qz * qw) * x
        + (1 - 2 * (qx * qx + qz * qz)) * y
        + 2 * (qy * qz - qx * qw) * z,
        2 * (qx * qz - qy * qw) * x
        + 2 * (qy * qz + qx * qw) * y
        + (1 - 2 * (qx * qx + qy * qy)) * z,
    )


def warehouse_map_to_odom_enu(
    coord: EnuCoordinate, warehouse_map_to_odom_tf: dict[str, Any]
) -> EnuCoordinate:
    """Apply inverse stored TF (pose of odom in warehouse_map) before control."""
    if coord.frame_id != "warehouse_map":
        raise ValueError("warehouse transform requires frame_id='warehouse_map'")
    translation = warehouse_map_to_odom_tf["translation"]
    rotation = warehouse_map_to_odom_tf["rotation"]
    rotation_values = [float(rotation[key]) for key in ("x", "y", "z", "w")]
    if not all(math.isfinite(value) for value in rotation_values):
        raise ValueError("warehouse transform quaternion must be finite")
    if abs(math.sqrt(sum(value * value for value in rotation_values)) - 1.0) > 1e-3:
        raise ValueError("warehouse transform quaternion must be normalized")
    shifted = (
        float(coord.x_m) - float(translation["x"]),
        float(coord.y_m) - float(translation["y"]),
        float(coord.z_m) - float(translation["z"]),
    )
    inverse = {
        "x": -float(rotation["x"]),
        "y": -float(rotation["y"]),
        "z": -float(rotation["z"]),
        "w": float(rotation["w"]),
    }
    x_m, y_m, z_m = _rotate(shifted, inverse)
    transform_yaw = math.atan2(
        2
        * (
            float(rotation["w"]) * float(rotation["z"])
            + float(rotation["x"]) * float(rotation["y"])
        ),
        1 - 2 * (float(rotation["y"]) ** 2 + float(rotation["z"]) ** 2),
    )
    return EnuCoordinate(
        x_m=x_m,
        y_m=y_m,
        z_m=z_m,
        yaw_rad=(
            normalize_angle_rad(coord.yaw_rad - transform_yaw)
            if coord.yaw_rad is not None
            else None
        ),
        frame_id="odom",
    )

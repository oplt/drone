from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Literal

from backend.modules.warehouse.schemas import WarehouseScanTargetCreate
from backend.modules.warehouse.service.coordinate_frames import validate_transform

RegisteredImportFrame = Literal["warehouse_map", "odom"]


def _multiply_quaternions(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    lx, ly, lz, lw = (left[key] for key in ("x", "y", "z", "w"))
    rx, ry, rz, rw = (right[key] for key in ("x", "y", "z", "w"))
    return {
        "x": lw * rx + lx * rw + ly * rz - lz * ry,
        "y": lw * ry - lx * rz + ly * rw + lz * rx,
        "z": lw * rz + lx * ry - ly * rx + lz * rw,
        "w": lw * rw - lx * rx - ly * ry - lz * rz,
    }


def _rotate(vector: tuple[float, float, float], q: dict[str, float]) -> tuple[float, float, float]:
    x, y, z = vector
    pure = {"x": x, "y": y, "z": z, "w": 0.0}
    conjugate = {"x": -q["x"], "y": -q["y"], "z": -q["z"], "w": q["w"]}
    rotated = _multiply_quaternions(_multiply_quaternions(q, pure), conjugate)
    return rotated["x"], rotated["y"], rotated["z"]


def _require_source_frame(payload: dict[str, Any], source_frame_id: str, label: str) -> None:
    actual = str(payload.get("frame_id") or source_frame_id)
    if actual != source_frame_id:
        raise ValueError(f"{label} frame_id must match import source_frame_id={source_frame_id!r}")
    payload["frame_id"] = source_frame_id


def _transform_point(payload: dict[str, Any], tf: dict[str, Any]) -> None:
    translation, rotation = tf["translation"], tf["rotation"]
    rotated = _rotate(tuple(float(payload[key]) for key in ("x_m", "y_m", "z_m")), rotation)
    payload.update(
        frame_id="warehouse_map",
        x_m=rotated[0] + translation["x"],
        y_m=rotated[1] + translation["y"],
        z_m=rotated[2] + translation["z"],
    )


def _transform_orientation(payload: dict[str, Any], tf: dict[str, Any]) -> None:
    orientation = payload.get("orientation")
    if not isinstance(orientation, dict):
        yaw = math.radians(float(payload.get("yaw_deg") or 0.0))
        orientation = {"x": 0.0, "y": 0.0, "z": math.sin(yaw / 2), "w": math.cos(yaw / 2)}
    payload["orientation"] = _multiply_quaternions(tf["rotation"], orientation)


def normalize_scan_target_import(
    raw_target: dict[str, Any],
    *,
    source_frame_id: RegisteredImportFrame,
    odom_to_warehouse_map_transform: dict[str, Any],
) -> WarehouseScanTargetCreate:
    """Validate a registered-frame import and emit canonical warehouse_map geometry."""
    target = deepcopy(raw_target)
    point = target.get("target_point_local_json")
    pose = target.get("scan_pose_local_json")
    if not isinstance(point, dict) or not isinstance(pose, dict):
        raise ValueError("Imported target requires target point and scan pose objects")
    _require_source_frame(point, source_frame_id, "target point")
    _require_source_frame(pose, source_frame_id, "scan pose")

    normal = target.get("shelf_normal_local_json")
    if normal is not None:
        if not isinstance(normal, dict):
            raise ValueError("shelf_normal_local_json must be an object")
        _require_source_frame(normal, source_frame_id, "shelf normal")
    aim = target.get("sensor_aim_json")
    if aim is not None:
        if not isinstance(aim, dict):
            raise ValueError("sensor_aim_json must be an object")
        _require_source_frame(aim, source_frame_id, "sensor aim")
        aim_point = aim.get("aim_point_local_json")
        if not isinstance(aim_point, dict):
            raise ValueError("sensor aim requires aim_point_local_json")
        _require_source_frame(aim_point, source_frame_id, "sensor aim point")

    if source_frame_id == "odom":
        tf = validate_transform(odom_to_warehouse_map_transform)
        _transform_point(point, tf)
        _transform_point(pose, tf)
        _transform_orientation(pose, tf)
        if normal is not None:
            rotated = _rotate(tuple(float(normal[key]) for key in ("x", "y", "z")), tf["rotation"])
            normal.update(frame_id="warehouse_map", x=rotated[0], y=rotated[1], z=rotated[2])
        if aim is not None:
            aim["frame_id"] = "warehouse_map"
            _transform_point(aim["aim_point_local_json"], tf)
            _transform_orientation(aim, tf)

    return WarehouseScanTargetCreate.model_validate(target)

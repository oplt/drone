from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.modules.warehouse.planning.indoor.enums import OccupancyState
from backend.modules.warehouse.planning.indoor.models import OccupancyGrid

_OCCUPANCY_ENCODING_V1 = "nav_msgs_occupancy_grid_i8_b64_v1"
OCCUPANCY_ENCODING_V2 = "nav_msgs_occupancy_grid_i8_b64_v2"
_OCCUPANCY_ENCODING_V2 = OCCUPANCY_ENCODING_V2


@dataclass(frozen=True)
class OccupancyGridOrigin:
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return {
            "x_m": float(self.x_m),
            "y_m": float(self.y_m),
            "z_m": float(self.z_m),
            "qx": float(self.qx),
            "qy": float(self.qy),
            "qz": float(self.qz),
            "qw": float(self.qw),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> OccupancyGridOrigin:
        if not isinstance(payload, dict):
            return cls()
        return cls(
            x_m=float(payload.get("x_m", payload.get("origin_x_m", 0.0)) or 0.0),
            y_m=float(payload.get("y_m", payload.get("origin_y_m", 0.0)) or 0.0),
            z_m=float(payload.get("z_m", payload.get("origin_z_m", 0.0)) or 0.0),
            qx=float(payload.get("qx", payload.get("origin_qx", 0.0)) or 0.0),
            qy=float(payload.get("qy", payload.get("origin_qy", 0.0)) or 0.0),
            qz=float(payload.get("qz", payload.get("origin_qz", 0.0)) or 0.0),
            qw=float(payload.get("qw", payload.get("origin_qw", 1.0)) or 1.0),
        )


@dataclass(frozen=True)
class OccupancyGridPayload:
    width: int
    height: int
    resolution_m: float
    origin: OccupancyGridOrigin
    frame_id: str
    data: np.ndarray

    @property
    def origin_x_m(self) -> float:
        return self.origin.x_m

    @property
    def origin_y_m(self) -> float:
        return self.origin.y_m

    @property
    def origin_z_m(self) -> float:
        return self.origin.z_m


def _parse_origin_pose(origin: Any) -> OccupancyGridOrigin:
    position = getattr(origin, "position", None) if origin is not None else None
    orientation = getattr(origin, "orientation", None) if origin is not None else None
    return OccupancyGridOrigin(
        x_m=float(getattr(position, "x", 0.0) or 0.0) if position is not None else 0.0,
        y_m=float(getattr(position, "y", 0.0) or 0.0) if position is not None else 0.0,
        z_m=float(getattr(position, "z", 0.0) or 0.0) if position is not None else 0.0,
        qx=float(getattr(orientation, "x", 0.0) or 0.0) if orientation is not None else 0.0,
        qy=float(getattr(orientation, "y", 0.0) or 0.0) if orientation is not None else 0.0,
        qz=float(getattr(orientation, "z", 0.0) or 0.0) if orientation is not None else 0.0,
        qw=float(getattr(orientation, "w", 1.0) or 1.0) if orientation is not None else 1.0,
    )


def _parse_origin_pose_dict(origin: dict[str, object] | None) -> OccupancyGridOrigin:
    if not isinstance(origin, dict):
        return OccupancyGridOrigin()
    position = origin.get("position")
    orientation = origin.get("orientation")
    position = position if isinstance(position, dict) else {}
    orientation = orientation if isinstance(orientation, dict) else {}
    return OccupancyGridOrigin(
        x_m=float(position.get("x") or 0.0),
        y_m=float(position.get("y") or 0.0),
        z_m=float(position.get("z") or 0.0),
        qx=float(orientation.get("x") or 0.0),
        qy=float(orientation.get("y") or 0.0),
        qz=float(orientation.get("z") or 0.0),
        qw=float(orientation.get("w") or 1.0),
    )


def parse_occupancy_grid_msg(msg: Any) -> OccupancyGridPayload | None:
    info = getattr(msg, "info", None)
    if info is None:
        return None
    width = int(getattr(info, "width", 0) or 0)
    height = int(getattr(info, "height", 0) or 0)
    resolution = float(getattr(info, "resolution", 0.0) or 0.0)
    if width <= 0 or height <= 0 or resolution <= 0.0:
        return None

    raw_values = getattr(msg, "data", None)
    raw = np.asarray([] if raw_values is None else raw_values, dtype=np.int16)
    expected = width * height
    if raw.size < expected:
        return None
    data = np.ascontiguousarray(raw[:expected].astype(np.int8, copy=False))

    origin = getattr(info, "origin", None)
    header = getattr(msg, "header", None)
    frame_id = str(getattr(header, "frame_id", "") or "").strip()
    if not frame_id:
        return None
    return OccupancyGridPayload(
        width=width,
        height=height,
        resolution_m=resolution,
        origin=_parse_origin_pose(origin),
        frame_id=frame_id,
        data=data,
    )


def occupancy_grid_bbox_local_m(
    *,
    width: int,
    height: int,
    resolution_m: float,
    origin: OccupancyGridOrigin,
) -> list[float]:
    """Axis-aligned world bbox for a grid with planar origin rotation."""
    yaw = math.atan2(
        2.0 * (origin.qw * origin.qz + origin.qx * origin.qy),
        1.0 - 2.0 * (origin.qy * origin.qy + origin.qz * origin.qz),
    )
    c = math.cos(yaw)
    s = math.sin(yaw)
    corners = (
        (0.0, 0.0),
        (float(width) * float(resolution_m), 0.0),
        (0.0, float(height) * float(resolution_m)),
        (float(width) * float(resolution_m), float(height) * float(resolution_m)),
    )
    xs: list[float] = []
    ys: list[float] = []
    for local_x, local_y in corners:
        world_x = (local_x * c) - (local_y * s)
        world_y = (local_x * s) + (local_y * c)
        xs.append(float(origin.x_m) + world_x)
        ys.append(float(origin.y_m) + world_y)
    return [
        min(xs),
        min(ys),
        float(origin.z_m),
        max(xs),
        max(ys),
        float(origin.z_m),
    ]


def encode_occupancy_grid(payload: OccupancyGridPayload) -> bytes:
    data = np.ascontiguousarray(payload.data, dtype=np.int8)
    body = {
        "encoding": _OCCUPANCY_ENCODING_V2,
        "width": int(payload.width),
        "height": int(payload.height),
        "resolution_m": float(payload.resolution_m),
        "origin": payload.origin.as_dict(),
        "frame_id": payload.frame_id,
        "data_b64": base64.b64encode(data.tobytes()).decode("ascii"),
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _origin_from_encoded_payload(payload: dict[str, object]) -> OccupancyGridOrigin:
    origin_payload = payload.get("origin")
    if isinstance(origin_payload, dict):
        return OccupancyGridOrigin.from_dict(origin_payload)
    return OccupancyGridOrigin(
        x_m=float(payload.get("origin_x_m", 0.0) or 0.0),
        y_m=float(payload.get("origin_y_m", 0.0) or 0.0),
    )


def decode_occupancy_grid(raw: bytes | str) -> OccupancyGrid | None:
    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        width = int(payload["width"])
        height = int(payload["height"])
        resolution = float(payload["resolution_m"])
        origin = _origin_from_encoded_payload(payload)
        raw_data = base64.b64decode(str(payload["data_b64"]))
    except (KeyError, TypeError, ValueError):
        return None
    data = np.frombuffer(raw_data, dtype=np.int8)
    if width <= 0 or height <= 0 or resolution <= 0.0 or data.size < width * height:
        return None

    grid = OccupancyGrid(
        resolution_m=resolution,
        width=width,
        height=height,
        origin_x_m=origin.x_m,
        origin_y_m=origin.y_m,
        origin_z_m=origin.z_m,
        origin_qx=origin.qx,
        origin_qy=origin.qy,
        origin_qz=origin.qz,
        origin_qw=origin.qw,
        default_state=OccupancyState.UNKNOWN,
    )
    values = data[: width * height].reshape((height, width))
    free_y, free_x = np.where((values >= 0) & (values <= 49))
    occupied_y, occupied_x = np.where(values >= 50)
    grid.set_cells(zip(free_x.tolist(), free_y.tolist(), strict=True), OccupancyState.FREE)
    grid.set_cells(
        zip(occupied_x.tolist(), occupied_y.tolist(), strict=True),
        OccupancyState.OCCUPIED,
    )
    return grid


def occupancy_grid_from_ros_yaml(payload: dict[str, object] | None) -> OccupancyGrid | None:
    """Decode the mapping returned by `ros2 topic echo --once` for OccupancyGrid."""
    if not isinstance(payload, dict):
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    origin = info.get("origin")
    origin = origin if isinstance(origin, dict) else {}
    try:
        width = int(info["width"])
        height = int(info["height"])
        resolution = float(info["resolution"])
        values = np.asarray(payload.get("data") or [], dtype=np.int8)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if width <= 0 or height <= 0 or resolution <= 0.0 or values.size < width * height:
        return None
    frame_id = (
        str((payload.get("header") or {}).get("frame_id") or "").strip()
        if isinstance(payload.get("header"), dict)
        else ""
    )
    if not frame_id:
        return None
    encoded = encode_occupancy_grid(
        OccupancyGridPayload(
            width=width,
            height=height,
            resolution_m=resolution,
            origin=_parse_origin_pose_dict(origin),
            frame_id=frame_id,
            data=np.ascontiguousarray(values[: width * height]),
        )
    )
    return decode_occupancy_grid(encoded)

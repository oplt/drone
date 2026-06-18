from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.modules.warehouse.planning.indoor.enums import OccupancyState
from backend.modules.warehouse.planning.indoor.models import OccupancyGrid


@dataclass(frozen=True)
class OccupancyGridPayload:
    width: int
    height: int
    resolution_m: float
    origin_x_m: float
    origin_y_m: float
    frame_id: str
    data: np.ndarray


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
    position = getattr(origin, "position", None) if origin is not None else None
    header = getattr(msg, "header", None)
    return OccupancyGridPayload(
        width=width,
        height=height,
        resolution_m=resolution,
        origin_x_m=float(getattr(position, "x", 0.0) or 0.0),
        origin_y_m=float(getattr(position, "y", 0.0) or 0.0),
        frame_id=str(getattr(header, "frame_id", "") or "odom"),
        data=data,
    )


def encode_occupancy_grid(payload: OccupancyGridPayload) -> bytes:
    data = np.ascontiguousarray(payload.data, dtype=np.int8)
    body = {
        "encoding": "nav_msgs_occupancy_grid_i8_b64_v1",
        "width": int(payload.width),
        "height": int(payload.height),
        "resolution_m": float(payload.resolution_m),
        "origin_x_m": float(payload.origin_x_m),
        "origin_y_m": float(payload.origin_y_m),
        "frame_id": payload.frame_id,
        "data_b64": base64.b64encode(data.tobytes()).decode("ascii"),
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


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
        origin_x = float(payload.get("origin_x_m", 0.0))
        origin_y = float(payload.get("origin_y_m", 0.0))
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
        origin_x_m=origin_x,
        origin_y_m=origin_y,
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

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseCoordinateFrame
from backend.modules.warehouse.service.drift_guard import validate_localization_evidence

WAREHOUSE_MAP_FRAME = "warehouse_map"
ODOM_FRAME = "odom"


def validate_transform(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    try:
        t = payload["translation"]
        q = payload["rotation"]
        translation = {axis: float(t[axis]) for axis in ("x", "y", "z")}
        rotation = {axis: float(q[axis]) for axis in ("x", "y", "z", "w")}
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "transform requires numeric translation{x,y,z} and rotation{x,y,z,w}"
        ) from exc
    if not all(math.isfinite(v) for v in (*translation.values(), *rotation.values())):
        raise ValueError("transform values must be finite")
    norm = math.sqrt(sum(v * v for v in rotation.values()))
    if norm < 1e-9:
        raise ValueError("rotation quaternion must be non-zero")
    if abs(norm - 1.0) > 1e-3:
        raise ValueError("rotation quaternion must be normalized")
    return {"translation": translation, "rotation": rotation}


def transform_odom_points(points: Any, transform: dict[str, Any]) -> Any:
    """Apply stored TF (warehouse_map parent, odom child) to Nx3 odom points."""
    import numpy as np

    tf = validate_transform(transform)
    q = tf["rotation"]
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    translation = np.array([tf["translation"][a] for a in ("x", "y", "z")])
    values = np.asarray(points)
    return values @ rotation.T + translation


def transform_warehouse_points(points: Any, transform: dict[str, Any]) -> Any:
    """Apply the inverse stored TF to Nx3 warehouse_map points."""
    import numpy as np

    tf = validate_transform(transform)
    q = tf["rotation"]
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    translation = np.array([tf["translation"][axis] for axis in ("x", "y", "z")])
    values = np.asarray(points)
    return (values - translation) @ rotation


async def get_locked_coordinate_frame(
    db: AsyncSession, warehouse_map_id: int
) -> WarehouseCoordinateFrame:
    row = (
        await db.execute(
            select(WarehouseCoordinateFrame)
            .where(
                WarehouseCoordinateFrame.warehouse_map_id == warehouse_map_id,
                WarehouseCoordinateFrame.status == "locked",
            )
            .order_by(WarehouseCoordinateFrame.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Warehouse coordinate frame is not localized and locked; mission planning is unsafe"
            ),
        )
    try:
        evidence = validate_localization_evidence(
            transform=row.transform_json,
            transform_timestamp=row.transform_timestamp,
            max_age_s=float(row.max_age_s),
            covariance=list(row.covariance_json or []),
            confidence=float(row.confidence or 0.0),
        )
    except ValueError as exc:
        raise HTTPException(409, f"Locked coordinate frame is unsafe: {exc}") from exc
    if row.transform_checksum != evidence["checksum_sha256"]:
        raise HTTPException(409, "Locked coordinate frame checksum mismatch")
    return row


def require_warehouse_map_frames(payloads: Iterable[dict[str, Any]]) -> None:
    frames = {str(value.get("frame_id") or "") for value in payloads}
    if frames != {WAREHOUSE_MAP_FRAME}:
        raise HTTPException(
            status_code=422, detail="Scan targets must use frame_id='warehouse_map'"
        )

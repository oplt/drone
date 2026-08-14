"""Warehouse coordinate-frame routes — response helpers."""

from __future__ import annotations

from backend.modules.warehouse.models import WarehouseCoordinateFrame

from .schemas import CoordinateFrameOut


def _out(row: WarehouseCoordinateFrame) -> CoordinateFrameOut:
    return CoordinateFrameOut(
        id=row.id,
        warehouse_map_id=row.warehouse_map_id,
        version=row.version,
        parent_frame_id=row.parent_frame_id,
        child_frame_id=row.child_frame_id,
        units=row.units,
        axis_convention=row.axis_convention,
        handedness=row.handedness,
        transform=row.transform_json,
        source=row.source,
        status=row.status,
        confidence=row.confidence,
        covariance=list(row.covariance_json or []),
        transform_timestamp=row.transform_timestamp,
        max_age_s=row.max_age_s,
        localization_method=row.localization_method,
        transform_checksum=row.transform_checksum,
        meta_data=dict(getattr(row, "meta_data", {}) or {}),
        created_at=row.created_at,
        locked_at=row.locked_at,
        superseded_at=row.superseded_at,
    )


__all__ = ["_out"]

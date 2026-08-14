"""Warehouse coordinate-frame routes — payload validation."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_write

from .commissioning import _commissioning_report
from .deps import get_map_or_404, transform_checksum
from .router import router
from .schemas import CoordinateFrameCreate, CoordinateFrameValidationOut


@router.post(
    "/maps/{warehouse_map_id}/coordinate-frame/validate",
    response_model=CoordinateFrameValidationOut,
)
async def validate_coordinate_frame_payload(
    warehouse_map_id: int,
    payload: CoordinateFrameCreate,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_write),
) -> CoordinateFrameValidationOut:
    await get_map_or_404(db, warehouse_map_id=warehouse_map_id, user=org_user.user)
    warnings = []
    if payload.confidence < 0.7:
        warnings.append(
            {"code": "localization_confidence_low", "message": "Frame cannot be locked below 0.7"}
        )
    if not payload.covariance:
        warnings.append(
            {"code": "covariance_missing", "message": "Locking requires a finite 6x6 covariance"}
        )
    commissioning_report = await _commissioning_report(
        db,
        warehouse_map_id=warehouse_map_id,
        payload=payload,
    )
    warnings.extend(commissioning_report.get("issues") or [])
    return CoordinateFrameValidationOut(
        valid=not warnings,
        validation_warnings=warnings,
        checksum_sha256=transform_checksum(payload.transform.model_dump()),
        commissioning_report=commissioning_report,
    )

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import require_user
from backend.modules.missions.flight_models import Flight
from backend.modules.patrol.models import PatrolDetection

router = APIRouter(prefix="/api/live-object-detection", tags=["live-object-detection"])


class LiveDetectionOut(BaseModel):
    id: int
    flight_id: int
    created_at: datetime
    label: str
    confidence: float
    bbox_xyxy: dict[str, Any]
    lat: float | None = None
    lon: float | None = None
    model_name: str | None = None
    meta_data: dict[str, Any]


@router.get("/detections", response_model=list[LiveDetectionOut])
async def list_live_detections(
    limit: int = Query(default=200, ge=1, le=1000),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> list[LiveDetectionOut]:
    filters = [PatrolDetection.source == "live_object_detection"]
    if user.org_id is not None:
        filters.append(Flight.org_id == user.org_id)
    stmt = (
        select(PatrolDetection)
        .join(Flight, Flight.id == PatrolDetection.flight_id)
        .where(*filters)
        .order_by(desc(PatrolDetection.created_at), desc(PatrolDetection.id))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [
        LiveDetectionOut(
            id=row.id,
            flight_id=row.flight_id,
            created_at=row.created_at,
            label=row.object_class,
            confidence=row.confidence,
            bbox_xyxy=row.bbox_xyxy,
            lat=row.lat,
            lon=row.lon,
            model_name=row.model_name,
            meta_data=row.meta_data,
        )
        for row in rows
    ]

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import require_user
from backend.modules.patrol.repository import PatrolDetectionRepository

router = APIRouter(prefix="/api/live-object-detection", tags=["live-object-detection"])
repository = PatrolDetectionRepository()


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
    user: Any = Depends(require_user),
    db: Any = Depends(get_db),
) -> list[LiveDetectionOut]:
    rows = await repository.list_live_object_detections(db, org_id=user.org_id, limit=limit)
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

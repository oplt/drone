from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import require_user
from backend.db.repository.alerts_repo import AlertRepository
from backend.db.session import get_db
from backend.messaging.websocket import telemetry_manager
from backend.schemas.alerts import AlertCountResponse, AlertListResponse, OperationalAlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
repo = AlertRepository()


def _alert_payload(alert) -> dict:
    return OperationalAlertOut.model_validate(alert).model_dump(mode="json")


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    status: str = Query(default="active", pattern="^(open|active|resolved|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await repo.list_alerts(db, status=status, limit=limit, offset=offset)
    return AlertListResponse(
        items=[OperationalAlertOut.model_validate(item) for item in items],
        total=total,
    )


@router.get("/open-count", response_model=AlertCountResponse)
async def open_alert_count(
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return AlertCountResponse(open_count=await repo.count_open_alerts(db))


@router.post("/{alert_id}/ack", response_model=OperationalAlertOut)
async def acknowledge_alert(
    alert_id: int,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await repo.acknowledge_alert(
        db,
        alert_id=alert_id,
        user_id=user.id,
        now=repo.utcnow(),
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.commit()
    await db.refresh(alert)
    await telemetry_manager.broadcast(
        {
            "type": "alert_event",
            "action": "acknowledged",
            "alert": _alert_payload(alert),
        }
    )
    return alert


@router.post("/{alert_id}/resolve", response_model=OperationalAlertOut)
async def resolve_alert(
    alert_id: int,
    user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await repo.resolve_by_id(
        db,
        alert_id=alert_id,
        now=repo.utcnow(),
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.commit()
    await db.refresh(alert)
    await telemetry_manager.broadcast(
        {
            "type": "alert_event",
            "action": "resolved",
            "alert": _alert_payload(alert),
        }
    )
    return alert

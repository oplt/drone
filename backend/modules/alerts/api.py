from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.core.events import (
    AlertEventEnvelopeV1,
    AlertEventPayloadV1,
    AlertSnapshotV1,
    mission_context_from_runtime,
    next_runtime_sequence,
    utc_now,
)
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.alerts.repository import AlertRepository
from backend.modules.alerts.schemas import (
    AlertCountResponse,
    AlertListResponse,
    OperationalAlertOut,
)
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_org_write
from backend.modules.patrol.service.mission_runtime_store import mission_runtime_store

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
repo = AlertRepository()


def _org_id(org_user: OrgUser) -> int:
    if org_user.org_id is None:
        raise HTTPException(status_code=403, detail="Organization membership required")
    return org_user.org_id


async def _alert_event_message(*, action: str, alert) -> dict:
    active_runtime = await mission_runtime_store.get_active_context()
    snapshot = AlertSnapshotV1.from_alert(alert)
    envelope = AlertEventEnvelopeV1(
        mission_runtime_id=getattr(active_runtime, "client_flight_id", None),
        db_flight_id=getattr(active_runtime, "db_flight_id", None),
        sequence=next_runtime_sequence(
            getattr(active_runtime, "client_flight_id", None),
            "alerts.api",
        ),
        emitted_at=utc_now(),
        source="alerts.api",
        mission=mission_context_from_runtime(active_runtime),
        payload=AlertEventPayloadV1(action=action, alert=snapshot),
    )
    return envelope.to_legacy_websocket_message()


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    status: str = Query(default="active", pattern="^(open|active|resolved|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await repo.list_alerts(
        db, org_id=_org_id(org_user), status=status, limit=limit, offset=offset
    )
    return AlertListResponse(
        items=[OperationalAlertOut.model_validate(item) for item in items],
        total=total,
    )


@router.get("/open-count", response_model=AlertCountResponse)
async def open_alert_count(
    org_user: OrgUser = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    return AlertCountResponse(open_count=await repo.count_open_alerts(db, org_id=_org_id(org_user)))


@router.post("/{alert_id}/ack", response_model=OperationalAlertOut)
async def acknowledge_alert(
    alert_id: int,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
):
    alert = await repo.acknowledge_alert(
        db,
        org_id=_org_id(org_user),
        alert_id=alert_id,
        user_id=org_user.user.id,
        now=repo.utcnow(),
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.commit()
    await db.refresh(alert)
    await telemetry_manager.broadcast(
        await _alert_event_message(action="acknowledged", alert=alert)
    )
    return alert


@router.post("/{alert_id}/resolve", response_model=OperationalAlertOut)
async def resolve_alert(
    alert_id: int,
    org_user: OrgUser = Depends(require_org_write),
    db: AsyncSession = Depends(get_db),
):
    alert = await repo.resolve_by_id(
        db,
        org_id=_org_id(org_user),
        alert_id=alert_id,
        now=repo.utcnow(),
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.commit()
    await db.refresh(alert)
    await telemetry_manager.broadcast(await _alert_event_message(action="resolved", alert=alert))
    return alert

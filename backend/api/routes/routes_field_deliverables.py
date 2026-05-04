"""Field deliverable sub-routes.

Prefix  : /fields  (included in the fields router via api_main.py)
Auth    : require_org_user (read) / require_org_write (create)
Models  : FieldDeliverable, Field

Routes:
  POST /fields/{field_id}/deliverables  — create + enqueue generation task
  GET  /fields/{field_id}/deliverables  — list deliverables for a field
"""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.auth.deps import OrgUser, require_org_user, require_org_write
from backend.db.models import Field, FieldDeliverable
from backend.db.session import Session
from backend.services.access_control import ownership_clause

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fields", tags=["deliverables"])

_VALID_TYPES = {"GEOJSON", "KML", "HTML_SUMMARY", "QA_CHECKLIST"}
_SHARE_LINK_TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DeliverableCreate(BaseModel):
    type: str  # GEOJSON | KML | HTML_SUMMARY | QA_CHECKLIST
    expires_in_days: int | None = _SHARE_LINK_TTL_DAYS


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deliverable_out(d: FieldDeliverable) -> dict[str, Any]:
    return {
        "id": d.id,
        "field_id": d.field_id,
        "org_id": d.org_id,
        "type": d.type,
        "status": d.status,
        "url": d.url,
        "share_token": d.share_token,
        "share_url": f"/share/{d.share_token}",
        "expires_at": d.expires_at.isoformat() if d.expires_at else None,
        "error": d.error,
        "created_at": d.created_at.isoformat(),
    }


async def _get_owned_field(field_id: int, org_user: OrgUser, db) -> Field:
    q = await db.execute(
        select(Field).where(
            Field.id == field_id,
            ownership_clause(
                user=org_user.user,
                owner_col=Field.owner_id,
                org_col=Field.org_id,
            ),
        )
    )
    field = q.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/{field_id}/deliverables", status_code=202)
async def create_deliverable(
    field_id: int,
    payload: DeliverableCreate,
    org_user: OrgUser = Depends(require_org_write),
) -> dict[str, Any]:
    """Enqueue a deliverable generation task for the given field.

    Returns 202 Accepted immediately; status transitions to 'ready' or 'failed'
    once the Celery worker finishes.
    """
    if payload.type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type. Must be one of: {', '.join(sorted(_VALID_TYPES))}",
        )

    async with Session() as db:
        field = await _get_owned_field(field_id, org_user, db)

        expires_at: datetime | None = None
        if payload.expires_in_days is not None and payload.expires_in_days > 0:
            expires_at = datetime.now(UTC) + timedelta(days=payload.expires_in_days)

        deliverable = FieldDeliverable(
            field_id=field.id,
            org_id=org_user.org_id if org_user.org_id else field.org_id,
            type=payload.type,
            status="pending",
            share_token=secrets.token_urlsafe(32),
            expires_at=expires_at,
            created_by_user_id=org_user.user.id,
        )
        db.add(deliverable)
        await db.commit()
        await db.refresh(deliverable)

    # Enqueue outside the DB transaction to avoid sending task before commit
    try:
        from backend.tasks.deliverable_tasks import generate_field_deliverable

        generate_field_deliverable.delay(deliverable.id)
        logger.info(
            "Enqueued deliverable generation: id=%s type=%s field=%s",
            deliverable.id,
            payload.type,
            field_id,
        )
    except Exception:
        logger.exception(
            "Failed to enqueue deliverable task for id=%s", deliverable.id
        )
        # The record is persisted in 'pending' state; operator can retry via admin

    return _deliverable_out(deliverable)


@router.get("/{field_id}/deliverables")
async def list_deliverables(
    field_id: int,
    org_user: OrgUser = Depends(require_org_user),
) -> list[dict[str, Any]]:
    """List all deliverables for a field, newest first."""
    async with Session() as db:
        # Verify ownership before listing
        await _get_owned_field(field_id, org_user, db)

        q = await db.execute(
            select(FieldDeliverable)
            .where(FieldDeliverable.field_id == field_id)
            .order_by(FieldDeliverable.created_at.desc())
        )
        deliverables = q.scalars().all()
        return [_deliverable_out(d) for d in deliverables]

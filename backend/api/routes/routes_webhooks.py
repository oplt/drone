from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from backend.auth.deps import OrgUser, require_org_user
from backend.db.models import WebhookDelivery, WebhookEndpoint
from backend.db.session import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENTS: set[str] = {"mission.completed", "mapping.ready", "alert.triggered"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class WebhookEndpointCreate(BaseModel):
    url: str
    events: list[str]

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("url must start with https:// or http://")
        return v

    @field_validator("events")
    @classmethod
    def events_must_be_valid(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_EVENTS
        if invalid:
            raise ValueError(
                f"Unknown event types: {sorted(invalid)}. "
                f"Valid: {sorted(VALID_EVENTS)}"
            )
        return v


class WebhookEndpointUpdate(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("url must start with https:// or http://")
        return v

    @field_validator("events")
    @classmethod
    def events_must_be_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            invalid = set(v) - VALID_EVENTS
            if invalid:
                raise ValueError(
                    f"Unknown event types: {sorted(invalid)}. "
                    f"Valid: {sorted(VALID_EVENTS)}"
                )
        return v


class WebhookEndpointOut(BaseModel):
    id: int
    org_id: int | None
    url: str
    events: list[Any]
    is_active: bool
    created_at: datetime
    # secret is intentionally omitted from the response

    model_config = {"from_attributes": True}


class WebhookDeliveryOut(BaseModel):
    id: int
    endpoint_id: int
    event_type: str
    status: str
    attempts: int
    last_attempted_at: datetime | None
    next_retry_at: datetime | None
    response_code: int | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/endpoints", response_model=list[WebhookEndpointOut])
async def list_endpoints(org_user: OrgUser = Depends(require_org_user)):
    """List all webhook endpoints for the org."""
    async with Session() as db:
        q = await db.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.org_id == org_user.org_id)
            .order_by(WebhookEndpoint.created_at.desc())
        )
        endpoints = q.scalars().all()
        return [WebhookEndpointOut.model_validate(ep) for ep in endpoints]


@router.post("/endpoints", response_model=WebhookEndpointOut, status_code=201)
async def create_endpoint(
    body: WebhookEndpointCreate,
    org_user: OrgUser = Depends(require_org_user),
):
    """
    Register a new webhook endpoint for the org.
    A signing secret is generated and stored; it is not returned in the response.
    Use X-Webhook-Signature (sha256=<hex>) to verify deliveries on your end.
    """
    if org_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no associated organisation")

    signing_secret = secrets.token_hex(32)  # 64-char hex string

    async with Session() as db:
        endpoint = WebhookEndpoint(
            org_id=org_user.org_id,
            url=body.url,
            events=body.events,
            secret=signing_secret,
            is_active=True,
            created_by_user_id=org_user.user.id,
        )
        db.add(endpoint)
        await db.commit()
        await db.refresh(endpoint)

    logger.info(
        "Webhook endpoint created",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "endpoint_id": endpoint.id,
            "url": body.url,
            "events": body.events,
        },
    )
    return WebhookEndpointOut.model_validate(endpoint)


@router.patch("/endpoints/{endpoint_id}", response_model=WebhookEndpointOut)
async def update_endpoint(
    endpoint_id: int,
    body: WebhookEndpointUpdate,
    org_user: OrgUser = Depends(require_org_user),
):
    """Update URL, subscribed events, or active status of a webhook endpoint."""
    async with Session() as db:
        q = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.org_id == org_user.org_id,
            )
        )
        endpoint = q.scalar_one_or_none()
        if endpoint is None:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        if body.url is not None:
            endpoint.url = body.url
        if body.events is not None:
            endpoint.events = body.events
        if body.is_active is not None:
            endpoint.is_active = body.is_active

        await db.commit()
        await db.refresh(endpoint)

    return WebhookEndpointOut.model_validate(endpoint)


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """Delete a webhook endpoint and all its delivery history (cascade)."""
    async with Session() as db:
        q = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.org_id == org_user.org_id,
            )
        )
        endpoint = q.scalar_one_or_none()
        if endpoint is None:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        await db.delete(endpoint)
        await db.commit()

    logger.info(
        "Webhook endpoint deleted",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "endpoint_id": endpoint_id,
        },
    )


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    endpoint_id: int | None = Query(default=None),
    org_user: OrgUser = Depends(require_org_user),
):
    """
    List webhook deliveries for the org (most recent first, max 100).
    Optionally filter by endpoint_id.
    """
    async with Session() as db:
        # Scope to org via join with endpoint
        stmt = (
            select(WebhookDelivery)
            .join(WebhookEndpoint, WebhookDelivery.endpoint_id == WebhookEndpoint.id)
            .where(WebhookEndpoint.org_id == org_user.org_id)
        )
        if endpoint_id is not None:
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)

        stmt = stmt.order_by(WebhookDelivery.created_at.desc()).limit(100)
        q = await db.execute(stmt)
        deliveries = q.scalars().all()
        return [WebhookDeliveryOut.model_validate(d) for d in deliveries]


@router.post("/deliveries/{delivery_id}/retry", status_code=202)
async def retry_delivery(
    delivery_id: int,
    org_user: OrgUser = Depends(require_org_user),
):
    """
    Re-enqueue a failed delivery. Only allowed when status=failed.
    Returns 202 Accepted — the actual delivery is asynchronous.
    """
    from backend.tasks.webhook_tasks import deliver_webhook

    async with Session() as db:
        # Load delivery and verify org ownership via endpoint
        q = await db.execute(
            select(WebhookDelivery)
            .join(WebhookEndpoint, WebhookDelivery.endpoint_id == WebhookEndpoint.id)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookEndpoint.org_id == org_user.org_id,
            )
        )
        delivery = q.scalar_one_or_none()
        if delivery is None:
            raise HTTPException(status_code=404, detail="Delivery not found")
        if delivery.status != "failed":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Delivery status is '{delivery.status}',"
                    " only 'failed' deliveries can be retried"
                ),
            )

        delivery.status = "pending"
        delivery.next_retry_at = None
        await db.commit()

    deliver_webhook.delay(delivery_id)
    logger.info(
        "Webhook delivery retry enqueued",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "delivery_id": delivery_id,
        },
    )
    return {"delivery_id": delivery_id, "status": "pending", "detail": "Retry enqueued"}

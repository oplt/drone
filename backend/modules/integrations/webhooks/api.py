from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.database.session import get_db
from backend.core.pagination import Page, clamp_page_limit, decode_offset_cursor, page_from_offset
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.integrations.webhooks.application import WebhookApplicationService
from backend.modules.integrations.webhooks.repository import WebhookRepository
from backend.modules.integrations.webhooks.schemas import (
    WebhookDeliveryOut,
    WebhookEndpointCreate,
    WebhookEndpointOut,
    WebhookEndpointUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
repository = WebhookRepository()
application = WebhookApplicationService(repository)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/endpoints", response_model=Page[WebhookEndpointOut])
async def list_endpoints(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    org_user: OrgUser = Depends(require_org_user),
    db: Any = Depends(get_db),
):
    """List all webhook endpoints for the org."""
    page_limit = clamp_page_limit(limit, maximum=100)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    endpoints = await repository.list_endpoints(
        db, org_id=org_user.org_id, offset=page_offset, limit=page_limit
    )
    return page_from_offset(
        [WebhookEndpointOut.model_validate(ep) for ep in endpoints],
        limit=page_limit,
        offset=page_offset,
    )


@router.post("/endpoints", response_model=WebhookEndpointOut, status_code=201)
async def create_endpoint(
    body: WebhookEndpointCreate,
    org_user: OrgUser = Depends(require_org_user),
    db: Any = Depends(get_db),
):
    """
    Register a new webhook endpoint for the org.
    A signing secret is generated and stored; it is not returned in the response.
    Use X-Webhook-Signature (sha256=<hex>) to verify deliveries on your end.
    """
    if org_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no associated organisation")

    signing_secret = secrets.token_hex(32)  # 64-char hex string

    endpoint = await repository.create_endpoint(
        db,
        org_id=org_user.org_id,
        user_id=org_user.user.id,
        url=body.url,
        events=body.events,
        secret=signing_secret,
    )

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
    db: Any = Depends(get_db),
):
    """Update URL, subscribed events, or active status of a webhook endpoint."""
    endpoint = await repository.endpoint_for_org(
        db, endpoint_id=endpoint_id, org_id=org_user.org_id
    )
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
    db: Any = Depends(get_db),
):
    """Delete a webhook endpoint and all its delivery history (cascade)."""
    if not await repository.delete_endpoint_for_org(
        db, endpoint_id=endpoint_id, org_id=org_user.org_id
    ):
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    logger.info(
        "Webhook endpoint deleted",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "endpoint_id": endpoint_id,
        },
    )


@router.get("/deliveries", response_model=Page[WebhookDeliveryOut])
async def list_deliveries(
    endpoint_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    org_user: OrgUser = Depends(require_org_user),
    db: Any = Depends(get_db),
):
    """
    List webhook deliveries for the org (most recent first, max 100 per page).
    Optionally filter by endpoint_id.
    """
    page_limit = clamp_page_limit(limit, maximum=100)
    page_offset = decode_offset_cursor(cursor) if cursor else offset
    deliveries = await repository.list_deliveries(
        db,
        org_id=org_user.org_id,
        endpoint_id=endpoint_id,
        offset=page_offset,
        limit=page_limit,
    )
    return page_from_offset(
        [WebhookDeliveryOut.model_validate(d) for d in deliveries],
        limit=page_limit,
        offset=page_offset,
    )


@router.post("/deliveries/{delivery_id}/retry", status_code=202)
async def retry_delivery(
    delivery_id: int,
    org_user: OrgUser = Depends(require_org_user),
    db: Any = Depends(get_db),
):
    """
    Re-enqueue a failed delivery. Only allowed when status=failed.
    Returns 202 Accepted — the actual delivery is asynchronous.
    """
    try:
        await application.retry_failed_delivery(
            db, delivery_id=delivery_id, org_id=org_user.org_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info(
        "Webhook delivery retry enqueued",
        extra={
            "org_id": org_user.org_id,
            "user_id": org_user.user.id,
            "delivery_id": delivery_id,
        },
    )
    return {"delivery_id": delivery_id, "status": "pending", "detail": "Retry enqueued"}

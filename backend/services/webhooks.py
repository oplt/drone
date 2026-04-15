"""Webhook dispatch service — fire-and-forget with delivery tracking."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def dispatch_event(
    db: AsyncSession,
    org_id: int | None,
    event_type: str,
    payload: dict,
) -> int:
    """
    Create WebhookDelivery rows for all active endpoints subscribed to event_type,
    then enqueue a deliver_webhook Celery task for each.

    Returns the number of deliveries enqueued.

    Callers must have an open DB session that will be committed after this
    function returns (or the caller can commit inline — flush() is called here
    to assign delivery IDs before enqueueing tasks).

    Design notes:
    - We flush() rather than commit() so the caller retains transaction control.
    - Tasks are enqueued after flush so the delivery row is visible to the worker
      if the caller commits. If the outer transaction rolls back, the orphaned
      task will fail to load the delivery and exit cleanly.
    - org_id=None is a no-op guard; system events with no org do not fan-out.
    """
    from backend.db.models import WebhookDelivery, WebhookEndpoint
    from backend.tasks.webhook_tasks import deliver_webhook

    if org_id is None:
        return 0

    q = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.org_id == org_id,
            WebhookEndpoint.is_active == True,  # noqa: E712
        )
    )
    endpoints = q.scalars().all()

    full_payload = {
        "event": event_type,
        "org_id": org_id,
        "data": payload,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    count = 0
    for ep in endpoints:
        if event_type not in (ep.events or []):
            continue

        delivery = WebhookDelivery(
            endpoint_id=ep.id,
            event_type=event_type,
            payload=full_payload,
            status="pending",
        )
        db.add(delivery)
        await db.flush()  # assigns delivery.id without committing

        deliver_webhook.delay(delivery.id)
        count += 1

    if count:
        logger.info(
            "Webhook event dispatched",
            extra={"org_id": org_id, "event_type": event_type, "deliveries": count},
        )

    return count

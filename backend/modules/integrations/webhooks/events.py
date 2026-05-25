"""Webhook dispatch service with durable delivery tracking."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.integrations.webhooks.service import webhook_dispatch_service


async def dispatch_event(
    db: AsyncSession,
    org_id: int | None,
    event_type: str,
    payload: dict,
) -> int:
    """
    Write one durable outbox event. The relay later creates endpoint deliveries.

    Returns the number of deliveries enqueued.

    Callers must have an open DB session that will be committed after this
    function returns (or the caller can commit inline; flush() is called here
    to assign delivery IDs before enqueueing tasks).

    Design notes:
    - We flush() rather than commit() so the caller retains transaction control.
    - Tasks are enqueued after flush so the delivery row is visible to the worker
      if the caller commits. If the outer transaction rolls back, the orphaned
      task will fail to load the delivery and exit cleanly.
    - org_id=None is a no-op guard; system events with no org do not fan-out.
    """
    payload_key = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]
    event = await webhook_dispatch_service.enqueue(
        db,
        org_id=org_id,
        event_type=event_type,
        payload=payload,
        idempotency_key=f"{event_type}:{payload_key}",
    )
    return 1 if event is not None else 0

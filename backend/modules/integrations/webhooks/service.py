from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from backend.core.database.session import Session
from backend.modules.automation.models import OutboxEvent
from backend.modules.automation.outbox_repository import OutboxRepository

from .repository import WebhookRepository

logger = logging.getLogger(__name__)


class WebhookDispatchService:
    def __init__(
        self,
        outbox: OutboxRepository | None = None,
        webhooks: WebhookRepository | None = None,
    ) -> None:
        self.outbox = outbox or OutboxRepository()
        self.webhooks = webhooks or WebhookRepository()

    async def enqueue(
        self,
        db,
        *,
        org_id: int | None,
        event_type: str,
        payload: dict,
        idempotency_key: str,
    ) -> OutboxEvent | None:
        if org_id is None:
            return None
        return await self.outbox.enqueue(
            db,
            event_type="webhook.dispatch",
            aggregate_type=event_type,
            aggregate_id=idempotency_key,
            idempotency_key=f"webhook:{idempotency_key}",
            payload={
                "event": event_type,
                "org_id": org_id,
                "data": payload,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    async def publish(self, event_id: int, enqueue_delivery: Callable[[int], object]) -> int:
        async with Session() as db:
            event = await self.outbox.get(db, event_id=event_id, for_update=True)
            if event is None or not await self.outbox.begin(db, event=event):
                await db.commit()
                return 0
            try:
                payload = event.payload or {}
                event_type = str(payload["event"])
                org_id = int(payload["org_id"])
                endpoints = await self.webhooks.subscribed_endpoints(
                    db, org_id=org_id, event_type=event_type
                )
                ids: list[int] = []
                for endpoint in endpoints:
                    delivery, created = await self.webhooks.create_delivery_once(
                        db,
                        endpoint_id=endpoint.id,
                        event_type=event_type,
                        payload=payload,
                        idempotency_key=f"{event.idempotency_key}:endpoint:{endpoint.id}",
                    )
                    if created or delivery.status != "delivered":
                        ids.append(delivery.id)
                await self.outbox.published(db, event=event)
                await db.commit()
            except Exception as exc:
                await self.outbox.failed(db, event=event, error=str(exc))
                await db.commit()
                raise

        for delivery_id in ids:
            try:
                enqueue_delivery(delivery_id)
            except Exception:
                logger.exception("Broker enqueue failed for webhook delivery id=%s", delivery_id)
        logger.info("Published outbox webhook event id=%s deliveries=%s", event_id, len(ids))
        return len(ids)


webhook_dispatch_service = WebhookDispatchService()

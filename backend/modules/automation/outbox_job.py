from __future__ import annotations

from collections.abc import Callable

from backend.core.database.session import Session
from backend.modules.alerts.notification_job import AlertNotificationJob
from backend.modules.integrations.webhooks.service import WebhookDispatchService

from .outbox_repository import OutboxRepository


class OutboxRelayJob:
    def __init__(
        self,
        repository: OutboxRepository | None = None,
        webhooks: WebhookDispatchService | None = None,
        alerts: AlertNotificationJob | None = None,
    ) -> None:
        self.repository = repository or OutboxRepository()
        self.webhooks = webhooks or WebhookDispatchService()
        self.alerts = alerts or AlertNotificationJob()

    async def pending_ids(self) -> list[int]:
        async with Session() as db:
            return await self.repository.pending_ids(db)

    async def publish(self, event_id: int, enqueue_delivery: Callable[[int], object]) -> int:
        async with Session() as db:
            event = await self.repository.get(db, event_id=event_id)
            if event is None:
                return 0
            event_type = event.event_type
            payload = event.payload or {}
            idempotency_key = event.idempotency_key
        if event_type == "webhook.dispatch":
            return await self.webhooks.publish(event_id, enqueue_delivery)
        if event_type != "alert.notify":
            raise ValueError(f"Unsupported outbox event type: {event_type}")

        async with Session() as db:
            event = await self.repository.get(db, event_id=event_id, for_update=True)
            if event is None or not await self.repository.begin(db, event=event):
                await db.commit()
                return 0
            await db.commit()
        try:
            await self.alerts.run(
                alert_id=int(payload["alert_id"]),
                payload=dict(payload["alert"]),
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            async with Session() as db:
                event = await self.repository.get(db, event_id=event_id)
                if event is not None:
                    await self.repository.failed(db, event=event, error=str(exc))
                    await db.commit()
            raise
        async with Session() as db:
            event = await self.repository.get(db, event_id=event_id)
            if event is not None:
                await self.repository.published(db, event=event)
                await db.commit()
        return 1

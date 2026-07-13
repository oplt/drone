"""Webhook use cases: transaction orchestration plus queue-port wiring."""

from __future__ import annotations

from typing import Any, Protocol

from backend.infrastructure.jobs import CeleryQueue
from backend.modules.integrations.webhooks.repository import WebhookRepository


class QueuePort(Protocol):
    def enqueue(self, task_name: str, *, queue: str | None = None, **kwargs: Any) -> str:
        ...


class WebhookApplicationService:
    def __init__(
        self,
        repository: WebhookRepository | None = None,
        queue: QueuePort | None = None,
    ) -> None:
        self.repository = repository or WebhookRepository()
        self.queue = queue or CeleryQueue()

    async def retry_failed_delivery(self, db: Any, *, delivery_id: int, org_id: int) -> None:
        delivery = await self.repository.delivery_for_org(
            db, delivery_id=delivery_id, org_id=org_id
        )
        if delivery is None:
            raise LookupError("Delivery not found")
        if delivery.status != "failed":
            raise ValueError(
                f"Delivery status is '{delivery.status}', only 'failed' deliveries can be retried"
            )
        delivery.status = "pending"
        delivery.next_retry_at = None
        await db.commit()
        self.queue.enqueue(
            "backend.tasks.webhook_tasks.deliver_webhook",
            queue="webhooks",
            delivery_id=delivery_id,
        )

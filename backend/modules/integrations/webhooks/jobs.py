from __future__ import annotations

import logging

from backend.core.config.runtime import settings
from backend.core.retry import retry_delay_seconds
from backend.core.database.session import Session
from backend.infrastructure.webhooks import HttpWebhookSender

from .repository import WebhookRepository

logger = logging.getLogger(__name__)
BACKOFF_SCHEDULE = (30, 300, 1800, 7200, 21600)


class WebhookRetryRequired(RuntimeError):
    def __init__(self, message: str, countdown: int) -> None:
        super().__init__(message)
        self.countdown = countdown


class WebhookDeliveryJob:
    def __init__(
        self,
        repository: WebhookRepository | None = None,
        sender: HttpWebhookSender | None = None,
    ) -> None:
        self.repository = repository or WebhookRepository()
        self.sender = sender or HttpWebhookSender()

    async def run(self, delivery_id: int) -> None:
        async with Session() as db:
            pair = await self.repository.delivery_and_endpoint(
                db, delivery_id=delivery_id, for_update=True
            )
            if pair is None:
                logger.warning("Webhook delivery %s no longer exists", delivery_id)
                return
            delivery, endpoint = pair
            if delivery.status == "delivered":
                return
            if not endpoint.is_active:
                await self.repository.failed(
                    db,
                    delivery=delivery,
                    error="Endpoint is inactive",
                    response_code=None,
                    retry_in_s=None,
                )
                await db.commit()
                return
            if not await self.repository.start_attempt(db, delivery=delivery):
                await db.commit()
                return
            await db.commit()

            response_code: int | None = None
            try:
                response = await self.sender.send(
                    url=endpoint.url,
                    secret=endpoint.secret,
                    event_type=delivery.event_type,
                    payload=delivery.payload,
                    timeout_s=settings.webhook_delivery_timeout_sec,
                )
                response_code = response.status_code
                if response.success:
                    await self.repository.delivered(
                        db, delivery=delivery, response_code=response.status_code
                    )
                    await db.commit()
                    return
                error = f"HTTP {response.status_code}"
            except Exception as exc:
                error = str(exc)

            retry_base_s = (
                BACKOFF_SCHEDULE[delivery.attempts - 1]
                if delivery.attempts <= len(BACKOFF_SCHEDULE)
                else None
            )
            retry_in_s = (
                retry_delay_seconds(
                    attempt=0,
                    base_seconds=retry_base_s,
                    max_seconds=retry_base_s,
                )
                if retry_base_s is not None
                else None
            )
            await self.repository.failed(
                db,
                delivery=delivery,
                error=error,
                response_code=response_code,
                retry_in_s=retry_in_s,
            )
            await db.commit()
            if retry_in_s:
                raise WebhookRetryRequired(error, retry_in_s)

    async def pending_ids(self) -> list[int]:
        async with Session() as db:
            return await self.repository.pending_ids(db)

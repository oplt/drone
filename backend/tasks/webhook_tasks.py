from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from backend.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Exponential backoff delays in seconds: 30s, 5m, 30m, 2h, 6h
_BACKOFF_SCHEDULE = [30, 300, 1800, 7200, 21600]


@celery_app.task(
    queue="webhooks",
    bind=True,
    max_retries=5,
    name="backend.tasks.webhook_tasks.deliver_webhook",
)
def deliver_webhook(self, delivery_id: int) -> None:
    """Celery task: deliver a single WebhookDelivery row with exponential backoff."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_deliver(self, delivery_id))
    finally:
        loop.close()


async def _deliver(task_self, delivery_id: int) -> None:
    import hmac
    import json

    import httpx

    from backend.config import settings
    from backend.db.models import WebhookDelivery, WebhookEndpoint
    from backend.db.session import Session

    async with Session() as db:
        delivery = await db.get(WebhookDelivery, delivery_id)
        if delivery is None:
            logger.error("WebhookDelivery %d not found — skipping", delivery_id)
            return

        endpoint = await db.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None:
            logger.error(
                "WebhookEndpoint %d not found for delivery %d — skipping",
                delivery.endpoint_id,
                delivery_id,
            )
            delivery.status = "failed"
            delivery.error = "Endpoint no longer exists"
            await db.commit()
            return

        if not endpoint.is_active:
            logger.warning(
                "Endpoint %d is inactive; marking delivery %d as failed",
                endpoint.id,
                delivery_id,
            )
            delivery.status = "failed"
            delivery.error = "Endpoint is inactive"
            await db.commit()
            return

        # Build body and HMAC-SHA256 signature
        body = json.dumps(delivery.payload, default=str).encode()
        sig = hmac.new(endpoint.secret.encode(), body, "sha256").hexdigest()

        delivery.attempts += 1
        delivery.last_attempted_at = datetime.now(UTC)

        try:
            async with httpx.AsyncClient(timeout=settings.webhook_delivery_timeout_sec) as client:
                resp = await client.post(
                    endpoint.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": f"sha256={sig}",
                        "X-Event-Type": delivery.event_type,
                    },
                )

            delivery.response_code = resp.status_code

            if resp.is_success:
                delivery.status = "delivered"
                delivery.next_retry_at = None
                logger.info(
                    "Webhook delivery %d succeeded (HTTP %d)",
                    delivery_id,
                    resp.status_code,
                )
                await db.commit()
                return

            # Non-2xx response — treat as retriable failure
            raise ValueError(f"HTTP {resp.status_code}")

        except Exception as exc:
            delivery.status = "failed"
            delivery.error = str(exc)[:500]

            attempt_index = delivery.attempts - 1  # 0-based
            if attempt_index < len(_BACKOFF_SCHEDULE):
                countdown = _BACKOFF_SCHEDULE[attempt_index]
                delivery.next_retry_at = datetime.now(UTC) + timedelta(
                    seconds=countdown
                )
                await db.commit()
                logger.warning(
                    "Webhook delivery %d failed (attempt %d); retrying in %ds: %s",
                    delivery_id,
                    delivery.attempts,
                    countdown,
                    exc,
                )
                raise task_self.retry(exc=exc, countdown=countdown) from exc

            # Exhausted retries
            delivery.next_retry_at = None
            await db.commit()
            logger.error(
                "Webhook delivery %d permanently failed after %d attempts: %s",
                delivery_id,
                delivery.attempts,
                exc,
            )

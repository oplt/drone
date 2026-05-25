from __future__ import annotations

import asyncio

from backend.entrypoints.workers.celery_app import celery_app
from backend.modules.integrations.webhooks.jobs import WebhookDeliveryJob, WebhookRetryRequired


@celery_app.task(
    queue="webhooks",
    bind=True,
    max_retries=5,
    name="backend.tasks.webhook_tasks.deliver_webhook",
    soft_time_limit=30,
    time_limit=45,
)
def deliver_webhook(self, delivery_id: int) -> None:
    try:
        asyncio.run(WebhookDeliveryJob().run(delivery_id))
    except WebhookRetryRequired as exc:
        raise self.retry(exc=exc, countdown=exc.countdown) from exc


@celery_app.task(queue="webhooks", name="backend.tasks.webhook_tasks.deliver_pending_webhooks")
def deliver_pending_webhooks() -> int:
    delivery_ids = asyncio.run(WebhookDeliveryJob().pending_ids())
    for delivery_id in delivery_ids:
        deliver_webhook.delay(delivery_id)
    return len(delivery_ids)

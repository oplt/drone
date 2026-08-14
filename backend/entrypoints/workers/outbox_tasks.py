from __future__ import annotations

from backend.core.retry import retry_delay_seconds
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.entrypoints.workers.celery_app import celery_app
from backend.entrypoints.workers.webhook_tasks import deliver_webhook
from backend.modules.automation.outbox_job import OutboxRelayJob

_worker_loop = WorkerLoopState()


@celery_app.task(
    queue="notifications",
    bind=True,
    max_retries=5,
    name="backend.tasks.outbox_tasks.publish_outbox_event",
    soft_time_limit=30,
    time_limit=45,
)
def publish_outbox_event(self, event_id: int) -> None:
    try:
        _worker_loop.run(OutboxRelayJob().publish(event_id, deliver_webhook.delay))
    except Exception as exc:
        raise self.retry(
            exc=exc,
            countdown=retry_delay_seconds(attempt=self.request.retries),
        ) from exc


@celery_app.task(
    queue="notifications",
    name="backend.tasks.outbox_tasks.publish_pending_outbox",
    soft_time_limit=30,
    time_limit=45,
)
def publish_pending_outbox() -> int:
    event_ids = _worker_loop.run(OutboxRelayJob().pending_ids())
    for event_id in event_ids:
        publish_outbox_event.delay(event_id)
    return len(event_ids)

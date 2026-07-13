"""Celery adapter; application modules depend on this port, never worker tasks."""

from __future__ import annotations

from typing import Any


class QueueEnqueueError(RuntimeError):
    pass


class CeleryQueue:
    def enqueue(self, task_name: str, *, queue: str | None = None, **kwargs: Any) -> str:
        try:
            from backend.entrypoints.workers.celery_app import celery_app
            from backend.observability.instruments import observed_span

            with observed_span("celery.enqueue", task_name=task_name, queue=queue or "default"):
                result = celery_app.send_task(task_name, kwargs=kwargs, queue=queue)
        except Exception as exc:
            raise QueueEnqueueError("Failed to enqueue background job") from exc
        task_id = getattr(result, "id", None)
        if not task_id:
            raise QueueEnqueueError("Queue backend did not return a task id")
        return str(task_id)


def enqueue_task(task_name: str, *, queue: str | None = None, **kwargs: Any) -> str:
    return CeleryQueue().enqueue(task_name, queue=queue, **kwargs)

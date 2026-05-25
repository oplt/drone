from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from backend.entrypoints.workers import deliverable_tasks, outbox_tasks

pytestmark = pytest.mark.integration


def test_deliverable_celery_adapter_executes_module_job(monkeypatch: Any) -> None:
    completed: list[int] = []

    class _Job:
        async def run(self, deliverable_id: int) -> None:
            completed.append(deliverable_id)

    monkeypatch.setattr(deliverable_tasks, "DeliverableGenerationJob", _Job)

    result = deliverable_tasks.generate_field_deliverable.apply(args=(41,), throw=True)

    assert result.successful()
    assert completed == [41]


def test_outbox_celery_adapter_executes_module_job(monkeypatch: Any) -> None:
    published: list[int] = []

    class _Job:
        async def publish(self, event_id: int, enqueue_delivery: Callable[[int], object]) -> int:
            published.append(event_id)
            return 0

    monkeypatch.setattr(outbox_tasks, "OutboxRelayJob", _Job)

    result = outbox_tasks.publish_outbox_event.apply(args=(27,), throw=True)

    assert result.successful()
    assert published == [27]

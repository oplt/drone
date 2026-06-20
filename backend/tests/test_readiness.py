import pytest

from backend.observability import readiness


@pytest.mark.asyncio
async def test_readiness_rejects_non_redis_broker(monkeypatch) -> None:
    monkeypatch.setattr(readiness.settings, "celery_broker_url", "amqp://broker")

    ready, details = await readiness.dependency_readiness()

    assert ready is False
    assert details["redis_broker"]["ready"] is False

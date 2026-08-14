from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.infrastructure.messaging.websocket_publisher import (
    TelemetryWebSocketManager,
    _record_telemetry_redis_fallback,
)
from backend.observability import prometheus_metrics


def test_telemetry_redis_fallback_metric_increments() -> None:
    before = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="publish_failed"
    )._value.get()
    _record_telemetry_redis_fallback("publish_failed")
    after = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="publish_failed"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_broadcast_bytes_records_publish_fallback() -> None:
    manager = TelemetryWebSocketManager()
    manager._redis = AsyncMock()
    manager._redis.publish = AsyncMock(side_effect=RuntimeError("redis down"))

    before = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="publish_failed"
    )._value.get()
    await manager.broadcast_bytes(b'{"type":"telemetry"}')
    after = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="publish_failed"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_initialize_records_redis_init_unavailable() -> None:
    manager = TelemetryWebSocketManager()
    before = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="init_unavailable"
    )._value.get()

    with patch(
        "redis.asyncio.from_url",
        side_effect=ConnectionError("redis unavailable"),
    ):
        await manager.initialize()

    after = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="init_unavailable"
    )._value.get()
    assert after == before + 1
    assert manager._redis is None


@pytest.mark.asyncio
async def test_subscriber_supervisor_reconnects_after_error(monkeypatch) -> None:
    manager = TelemetryWebSocketManager()
    calls = {"count": 0}

    async def flaky_subscriber() -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("pubsub dropped")
        manager._shutting_down = True

    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "backend.infrastructure.messaging.websocket_publisher.asyncio.sleep",
        sleep_mock,
    )
    monkeypatch.setattr(manager, "_redis_subscriber", flaky_subscriber)

    before = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="subscriber_reconnect"
    )._value.get()

    await manager._run_redis_subscriber()

    assert calls["count"] == 2
    after = prometheus_metrics.telemetry_redis_fallback_total.labels(
        reason="subscriber_reconnect"
    )._value.get()
    assert after == before + 1
    sleep_mock.assert_awaited_once()

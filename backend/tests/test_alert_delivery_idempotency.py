from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.alerts.models import AlertDelivery
from backend.modules.alerts.repository import AlertRepository


@pytest.mark.asyncio
async def test_record_delivery_returns_existing_row_for_idempotency_key() -> None:
    repo = AlertRepository()
    db = AsyncMock()
    existing = AlertDelivery(
        id=42,
        alert_id=7,
        channel="email",
        destination="ops@example.com",
        status="sent",
        payload={},
        idempotency_key="alert.notify:7:2026-08-14T10:00:00",
    )
    db.scalar = AsyncMock(return_value=existing)

    result = await repo.record_delivery(
        db,
        alert_id=7,
        channel="email",
        destination="ops@example.com",
        status="sent",
        payload={"subject": "test"},
        idempotency_key="alert.notify:7:2026-08-14T10:00:00",
    )

    assert result is existing
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_delivery_inserts_when_idempotency_key_is_new() -> None:
    repo = AlertRepository()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()

    result = await repo.record_delivery(
        db,
        alert_id=3,
        channel="webhook",
        destination="https://example.com/hook",
        status="queued",
        payload={"event": "alert"},
        idempotency_key="alert.notify:3:2026-08-14T10:00:00",
    )

    assert result.alert_id == 3
    assert result.idempotency_key == "alert.notify:3:2026-08-14T10:00:00"
    db.add.assert_called_once()
    db.flush.assert_awaited_once()

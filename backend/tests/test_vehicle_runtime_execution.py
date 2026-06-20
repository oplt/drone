import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.modules.vehicle_runtime import execution_service


def test_waits_configured_grace_when_telemetry_was_started(monkeypatch) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(execution_service.asyncio, "sleep", sleep)

    asyncio.run(execution_service._wait_for_telemetry_startup(started=True, grace_s=0.25))

    sleep.assert_awaited_once_with(0.25)


@pytest.mark.parametrize(
    ("started", "grace_s"),
    [(False, 1.0), (True, 0.0)],
)
def test_skips_grace_when_not_needed(monkeypatch, started: bool, grace_s: float) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(execution_service.asyncio, "sleep", sleep)

    asyncio.run(
        execution_service._wait_for_telemetry_startup(started=started, grace_s=grace_s)
    )

    sleep.assert_not_awaited()

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.telemetry.websocket_api import (
    _authenticate_websocket,
    _record_websocket_auth_failure,
)
from backend.observability import prometheus_metrics
from backend.observability.database import observed_db_session_scope
from backend.observability.event_loop_lag import EventLoopLagMonitor


@pytest.mark.asyncio
async def test_websocket_auth_failure_metric_labels(monkeypatch) -> None:
    before = prometheus_metrics.websocket_auth_failures_total.labels(
        reason="query_string_token"
    )._value.get()

    socket = SimpleNamespace(
        query_params={"token": "leaked"},
        headers={},
        cookies={},
    )
    user, error = await _authenticate_websocket(socket)
    assert user is None
    assert error is not None

    after = prometheus_metrics.websocket_auth_failures_total.labels(
        reason="query_string_token"
    )._value.get()
    assert after == before + 1


def test_websocket_auth_failure_reason_metric_helper() -> None:
    before = prometheus_metrics.websocket_auth_failures_total.labels(
        reason="missing_token"
    )._value.get()
    _record_websocket_auth_failure("missing_token")
    after = prometheus_metrics.websocket_auth_failures_total.labels(
        reason="missing_token"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_event_loop_lag_monitor_sets_metric() -> None:
    monitor = EventLoopLagMonitor(interval_s=0.05)
    await monitor.start()
    await asyncio.sleep(0.15)
    await monitor.stop()
    assert prometheus_metrics.event_loop_lag_seconds._value.get() >= 0.0


@pytest.mark.asyncio
async def test_run_blocking_records_boundary_duration() -> None:
    before = prometheus_metrics.blocking_boundary_duration_seconds.labels(
        boundary="cpu",
        operation="test_sleep",
    )._sum.get()

    await run_blocking(
        lambda: None,
        boundary="cpu",
        operation="test_sleep",
    )

    after = prometheus_metrics.blocking_boundary_duration_seconds.labels(
        boundary="cpu",
        operation="test_sleep",
    )._sum.get()
    assert after >= before


@pytest.mark.asyncio
async def test_observed_db_session_scope_records_hold_duration() -> None:
    metric = prometheus_metrics.db_session_hold_duration_seconds.labels(scope="test.scope")
    before = metric._sum.get()

    async with observed_db_session_scope(scope="test.scope"):
        await asyncio.sleep(0.01)

    after = metric._sum.get()
    assert after > before


def test_celery_app_imports_with_soft_time_limit_failure_hook() -> None:
    from celery import signals

    from backend.entrypoints.workers.celery_app import celery_app

    assert celery_app.conf.task_routes
    assert signals.task_failure.receivers

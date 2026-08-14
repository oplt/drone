from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.core.config.runtime import settings
from backend.core.rate_limit import enforce_rate_limit


@pytest.mark.asyncio
async def test_video_analysis_upload_rate_limit_returns_429(monkeypatch) -> None:
    import backend.core.rate_limit as rate_limit

    monkeypatch.setattr(
        rate_limit,
        "get_redis_client",
        lambda: (_ for _ in ()).throw(ConnectionError("redis unavailable")),
    )
    key = "video-analysis:upload:99"
    await enforce_rate_limit(
        key=key,
        limit=1,
        window_seconds=settings.api_rate_window_seconds,
    )
    with pytest.raises(HTTPException) as exc_info:
        await enforce_rate_limit(
            key=key,
            limit=1,
            window_seconds=settings.api_rate_window_seconds,
        )
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_agents_run_rate_limit_returns_429(monkeypatch) -> None:
    import backend.core.rate_limit as rate_limit

    monkeypatch.setattr(
        rate_limit,
        "get_redis_client",
        lambda: (_ for _ in ()).throw(ConnectionError("redis unavailable")),
    )
    key = "agents:run:42"
    await enforce_rate_limit(
        key=key,
        limit=settings.agents_rate_runs_per_window,
        window_seconds=settings.api_rate_window_seconds,
    )
    for _ in range(settings.agents_rate_runs_per_window - 1):
        await enforce_rate_limit(
            key=key,
            limit=settings.agents_rate_runs_per_window,
            window_seconds=settings.api_rate_window_seconds,
        )
    with pytest.raises(HTTPException) as exc_info:
        await enforce_rate_limit(
            key=key,
            limit=settings.agents_rate_runs_per_window,
            window_seconds=settings.api_rate_window_seconds,
        )
    assert exc_info.value.status_code == 429

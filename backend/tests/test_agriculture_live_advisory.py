from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.modules.agriculture.routers import common as agriculture_common
from backend.modules.agriculture.routers import live as agriculture_live


def test_live_advisory_offloads_cpu_work_via_run_blocking(monkeypatch) -> None:
    agriculture_common._live_processors.clear()
    run_blocking = AsyncMock(
        return_value=SimpleNamespace(
            frame_index=1,
            timestamp_seconds=0.5,
            state="clear",
            alerts=[],
            geolocation=None,
            expires_at=2.0,
        )
    )
    monkeypatch.setattr(agriculture_live, "run_blocking", run_blocking)
    monkeypatch.setattr(agriculture_common, "decode_rgb_frame", lambda _data: object())
    monkeypatch.setattr(agriculture_common, "_owned_flight", AsyncMock())
    monkeypatch.setattr(agriculture_common, "enforce_rate_limit", AsyncMock())

    class FrameUpload:
        async def read(self):
            return b"encoded-frame"

    async def _call_live_advisory():
        return await agriculture_live.live_advisory(
            "flight-1",
            FrameUpload(),
            0.5,
            None,
            None,
            SimpleNamespace(id="flight-1"),
        )

    advisory = asyncio.run(_call_live_advisory())

    run_blocking.assert_awaited_once()
    assert run_blocking.await_args.kwargs["operation"] == "agriculture_live_advisory"
    assert advisory.state == "clear"
    assert advisory.source_of_truth == "provisional_live"
    agriculture_common._live_processors.clear()

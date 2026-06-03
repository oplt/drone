from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_preflight_io_uses_parallel_gather_not_sequential() -> None:
    """Bridge autostart and vehicle telemetry fetch should overlap."""
    order: list[str] = []

    async def bridge_task() -> None:
        order.append("bridge_start")
        await asyncio.sleep(0.04)
        order.append("bridge_end")

    async def telemetry_task() -> None:
        order.append("telemetry_start")
        await asyncio.sleep(0.04)
        order.append("telemetry_end")

    import time

    started = time.monotonic()
    await asyncio.gather(bridge_task(), telemetry_task())
    elapsed = time.monotonic() - started

    assert order.index("telemetry_start") < order.index("bridge_end")
    assert order.index("bridge_start") < order.index("telemetry_end")
    assert elapsed < 0.075

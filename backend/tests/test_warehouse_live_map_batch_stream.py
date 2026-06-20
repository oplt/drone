import asyncio
from contextlib import nullcontext

from backend.modules.warehouse.routers import live_map


def test_batch_stream_emits_fast_resolution_before_slow_lookup(monkeypatch) -> None:
    release_slow: asyncio.Event | None = None

    def resolve(*, flight_id: str, chunk_id: str):
        assert flight_id == "flight-1"
        return None

    async def to_thread(function, *args, **kwargs):
        if kwargs.get("chunk_id") == "slow":
            assert release_slow is not None
            await release_slow.wait()
        return function(*args, **kwargs)

    monkeypatch.setattr(live_map.warehouse_live_map_chunk_storage, "resolve", resolve)
    monkeypatch.setattr(live_map, "observed_span", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(live_map.asyncio, "to_thread", to_thread)

    async def run() -> None:
        nonlocal release_slow
        release_slow = asyncio.Event()
        response = await live_map.live_map_chunk_batch_download(
            "flight-1",
            live_map.WarehouseLiveMapChunkBatchIn(chunk_ids=["slow", "fast"]),
            None,
        )
        iterator = response.body_iterator.__aiter__()
        try:
            first_frame = await asyncio.wait_for(anext(iterator), timeout=0.5)
            assert b'"chunk_id":"fast"' in first_frame
        finally:
            release_slow.set()
            await iterator.aclose()

    asyncio.run(run())

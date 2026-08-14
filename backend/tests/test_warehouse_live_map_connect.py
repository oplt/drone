from __future__ import annotations

import pytest

from backend.modules.warehouse.service.live_map_stream import (
    DEFAULT_WS_CONNECT_SNAPSHOT_MAX_UPDATES,
    WarehouseLiveMapStream,
    WarehouseLiveMapUpdate,
)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_live_map_connect_snapshot_is_bounded() -> None:
    stream = WarehouseLiveMapStream(
        connect_snapshot_max_updates=3,
        max_updates_per_flight=100,
    )
    flight_id = "flight-1"
    for _index in range(10):
        await stream.publish(
            WarehouseLiveMapUpdate(
                flight_id=flight_id,
                frame_id="odom",
                changed_chunks=[],
            )
        )

    socket = _FakeWebSocket()
    await stream.connect(flight_id, socket)  # type: ignore[arg-type]

    assert len(socket.sent) == 1
    snapshot = socket.sent[0]
    assert snapshot["type"] == "live_map_snapshot"
    assert snapshot["total_buffered_updates"] == 10
    assert snapshot["snapshot_truncated"] is True
    assert len(snapshot["updates"]) == 3


def test_live_map_default_connect_snapshot_limit() -> None:
    assert DEFAULT_WS_CONNECT_SNAPSHOT_MAX_UPDATES == 32


@pytest.mark.asyncio
async def test_live_map_redis_publish_called_on_local_publish(monkeypatch) -> None:
    stream = WarehouseLiveMapStream()
    published: list[tuple[str, dict]] = []

    async def fake_publish(*, flight_id: str, payload: dict) -> None:
        published.append((flight_id, payload))

    monkeypatch.setattr(stream, "_publish_redis", fake_publish)

    update = WarehouseLiveMapUpdate(flight_id="flight-2", frame_id="odom")
    await stream.publish(update)

    assert published == [("flight-2", update.model_dump(mode="json"))]

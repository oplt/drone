from types import SimpleNamespace

import pytest

from backend.modules.warehouse.routers import live_map


class _Socket:
    def __init__(self) -> None:
        self.closed: tuple[int, str | None] | None = None

    async def close(self, *, code: int, reason: str | None = None) -> None:
        self.closed = (code, reason)


@pytest.mark.asyncio
async def test_live_map_websocket_rejects_cross_org_flight(monkeypatch) -> None:
    socket = _Socket()

    async def authenticate(_socket):
        return SimpleNamespace(id=1, org_id=10), None

    async def runtime(_flight_id):
        return SimpleNamespace(org_id=20)

    monkeypatch.setattr(live_map, "_authenticate_websocket", authenticate)
    monkeypatch.setattr(live_map.mission_application, "get_by_client_id", runtime)

    await live_map.websocket_live_map_stream(socket, "flight-other-org")

    assert socket.closed is not None
    assert socket.closed[0] == 1008
    assert "organization" in (socket.closed[1] or "")

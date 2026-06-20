import asyncio
from unittest.mock import AsyncMock

from backend.modules.warehouse.routers import live_map
from backend.modules.warehouse.service.live_map_stream import WarehouseLiveMapSnapshot


def test_http_snapshot_limits_update_history(monkeypatch) -> None:
    snapshot = AsyncMock(
        return_value=WarehouseLiveMapSnapshot(flight_id="flight-1")
    )
    monkeypatch.setattr(live_map.warehouse_live_map_stream, "snapshot", snapshot)

    response = asyncio.run(live_map.live_map_snapshot("flight-1", None))

    assert response.flight_id == "flight-1"
    snapshot.assert_awaited_once_with(
        "flight-1",
        max_updates=live_map.WAREHOUSE_LIVE_MAP_HTTP_SNAPSHOT_MAX_UPDATES,
    )

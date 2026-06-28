import asyncio

import pytest
from pydantic import ValidationError

from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveMapStream,
    WarehouseLiveMapUpdate,
)


def _update(frame_id: str = "odom") -> WarehouseLiveMapUpdate:
    return WarehouseLiveMapUpdate.model_validate(
        {
            "flight_id": "flight-1",
            "frame_id": frame_id,
            "changed_chunks": [{"id": "chunk-1", "kind": "point_cloud", "frame_id": frame_id}],
        }
    )


def test_live_map_update_requires_explicit_frame() -> None:
    with pytest.raises(ValidationError, match="frame_id"):
        WarehouseLiveMapUpdate.model_validate({"flight_id": "flight-1"})


def test_live_map_update_rejects_nested_frame_mismatch(caplog) -> None:
    with caplog.at_level("WARNING"), pytest.raises(ValidationError, match="conflicts"):
        WarehouseLiveMapUpdate.model_validate(
            {
                "flight_id": "flight-1",
                "frame_id": "odom",
                "changed_chunks": [
                    {"id": "chunk-1", "kind": "point_cloud", "frame_id": "warehouse_map"}
                ],
            }
        )
    assert "warehouse_live_map_frame_mismatch" in caplog.text


def test_live_map_update_rejects_unregistered_map_alias() -> None:
    with pytest.raises(ValidationError, match="one of"):
        _update("map")


def test_chunk_only_update_does_not_fabricate_pose() -> None:
    assert _update().pose is None


def test_stream_rejects_midflight_frame_change() -> None:
    stream = WarehouseLiveMapStream()
    asyncio.run(stream.publish(_update("odom")))
    with pytest.raises(ValueError, match="frame changed"):
        asyncio.run(stream.publish(_update("warehouse_map")))

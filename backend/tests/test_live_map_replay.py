from __future__ import annotations

import struct
from pathlib import Path

import pytest

from backend.modules.warehouse.service import live_map_replay
from backend.modules.warehouse.service.live_map_storage import WarehouseLiveMapChunkStorage
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveMapStream,
    normalize_live_map_payload,
)


def test_live_map_chunk_batch_in_accepts_chunk_ids() -> None:
    from pydantic import ValidationError

    from backend.modules.warehouse.api import WarehouseLiveMapChunkBatchIn

    payload = WarehouseLiveMapChunkBatchIn(chunk_ids=["rgbd_000001", "mid360_000002"])
    assert payload.chunk_ids == ["rgbd_000001", "mid360_000002"]
    assert payload.model_dump() == {"chunk_ids": ["rgbd_000001", "mid360_000002"]}

    with pytest.raises(ValidationError):
        WarehouseLiveMapChunkBatchIn.model_validate({"chunk_ids": "rgbd_000001"})


class _FakeWebSocket:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("client stuck")
        self.sent.append(payload)


def test_infer_chunk_metadata_rgbd_xyzrgb32() -> None:
    path = Path("rgbd_000001-deadbeefcafebabe.xyzrgb32")
    metadata = live_map_replay._infer_chunk_metadata("rgbd_000001", path)

    assert metadata == {
        "kind": "point_cloud",
        "encoding": "xyzrgb32_v1",
        "has_rgb": True,
        "source": "rgbd_colored",
        "layer": "rgbd_colored",
        "sequence": 1,
    }


def test_infer_chunk_metadata_mid360_xyz32() -> None:
    path = Path("mid360_000001-deadbeefcafebabe.xyz32")
    metadata = live_map_replay._infer_chunk_metadata("mid360_000001", path)

    assert metadata == {
        "kind": "point_cloud",
        "encoding": "xyz32_v1",
        "has_rgb": False,
        "source": "mid360_raw",
        "layer": "mid360_lidar",
        "sequence": 1,
    }


def test_infer_chunk_metadata_does_not_classify_xyzrgb32_as_mesh() -> None:
    path = Path("rgbd_000010-0123456789abcdef.xyzrgb32")
    metadata = live_map_replay._infer_chunk_metadata("rgbd_000010", path)
    assert metadata["kind"] == "point_cloud"
    assert metadata["encoding"] == "xyzrgb32_v1"


def test_build_disk_live_map_snapshot_replays_colored_and_raw_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_test_replay"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()

    rgb_payload = struct.pack("<ffffff", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    rgb_payload += bytes([255, 0, 0, 0, 255, 0])
    (flight_dir / "rgbd_000001-deadbeefcafebabe.xyzrgb32").write_bytes(rgb_payload)

    mid_payload = struct.pack("<ffffff", 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    (flight_dir / "mid360_000001-feedfacefeedface.xyz32").write_bytes(mid_payload)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_replay,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    snapshot = live_map_replay.build_disk_live_map_snapshot(flight_id)
    assert snapshot.status == "finalized"
    assert len(snapshot.updates) == 1

    chunks = snapshot.updates[0].changed_chunks
    by_id = {chunk.id: chunk for chunk in chunks}

    rgbd = by_id["rgbd_000001"]
    assert rgbd.kind == "point_cloud"
    assert rgbd.source == "rgbd_colored"
    assert rgbd.layer == "rgbd_colored"
    assert rgbd.has_rgb is True
    assert rgbd.encoding == "xyzrgb32_v1"

    mid360 = by_id["mid360_000001"]
    assert mid360.kind == "point_cloud"
    assert mid360.source == "mid360_raw"
    assert mid360.layer == "mid360_lidar"
    assert mid360.has_rgb is False
    assert mid360.encoding == "xyz32_v1"


def test_build_disk_live_map_snapshot_returns_all_manifest_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_many_chunks"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()

    for sequence in range(1, 6):
        payload = struct.pack("<ffffff", float(sequence), 0.0, 0.0, 1.0, 1.0, 1.0)
        payload += bytes([255, 0, 0, 0, 255, 0])
        chunk_id = f"rgbd_{sequence:06d}"
        (flight_dir / f"{chunk_id}-deadbeefcafebabe.xyzrgb32").write_bytes(payload)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_replay,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    snapshot = live_map_replay.build_disk_live_map_snapshot(flight_id, mode="full")
    assert len(snapshot.updates[0].changed_chunks) == 5


def test_build_disk_live_map_snapshot_is_disk_backed_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_disk_source"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    payload = struct.pack("<ffffff", 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    (flight_dir / "rgbd_000001-deadbeefcafebabe.xyzrgb32").write_bytes(payload)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_replay,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    snapshot = live_map_replay.build_disk_live_map_snapshot(flight_id)

    assert snapshot.flight_id == flight_id
    assert snapshot.status == "finalized"
    assert len(snapshot.updates) == 1
    assert len(snapshot.updates[0].changed_chunks) == 1
    assert snapshot.updates[0].changed_chunks[0].id == "rgbd_000001"


@pytest.mark.asyncio
async def test_live_map_publish_removes_slow_client_without_blocking_fast_client() -> None:
    stream = WarehouseLiveMapStream()
    fast = _FakeWebSocket()
    slow = _FakeWebSocket(fail=True)
    async with stream._lock:
        stream._clients["flight"] = {fast, slow}  # type: ignore[arg-type]

    update = normalize_live_map_payload(
        {
            "flight_id": "flight",
            "changed_chunks": [{"id": "rgbd_000001", "kind": "point_cloud"}],
        }
    )

    await stream.publish(update)

    assert len(fast.sent) == 1
    async with stream._lock:
        assert slow not in stream._clients["flight"]  # type: ignore[comparison-overlap]

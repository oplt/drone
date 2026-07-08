from __future__ import annotations

import json
import struct
import time
from pathlib import Path
from typing import Any

import pytest

from backend.modules.warehouse.service import live_map_manifest
from backend.modules.warehouse.service.capture import WarehouseCaptureSessionService
from backend.modules.warehouse.service.live_map_storage import WarehouseLiveMapChunkStorage


class _MemoryUpload:
    content_type = "application/octet-stream"

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        if size < 0:
            size = len(self._payload) - self._offset
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def _write_rgbd_chunk(flight_dir: Path, sequence: int = 1, *, has_rgb: bool = True) -> None:
    payload = struct.pack("<ffffff", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    payload += bytes([255, 0, 0, 0, 255, 0])
    chunk_id = f"rgbd_{sequence:06d}"
    (flight_dir / f"{chunk_id}-deadbeefcafebabe.xyzrgb32").write_bytes(payload)
    meta = {
        "source": "rgbd_colored",
        "layer": "rgbd_colored",
        "layer_type": "rgbd_colored",
        "has_rgb": has_rgb,
        "point_count": 2,
        "encoding": "xyzrgb32_v1",
    }
    (flight_dir / f"{chunk_id}-deadbeefcafebabe.meta.json").write_text(
        json.dumps(meta),
        encoding="utf-8",
    )


def _write_internal_nvblox_color_chunk(flight_dir: Path) -> None:
    chunk_id = "nvblox_color_000001"
    payload = struct.pack("<fff", 1.0, 2.0, 3.0) + bytes([255, 0, 0])
    (flight_dir / f"{chunk_id}-cafebabecafebabe.xyzrgb32").write_bytes(payload)
    (flight_dir / f"{chunk_id}-cafebabecafebabe.meta.json").write_text(
        json.dumps(
            {
                "source": "nvblox_color",
                "layer": "nvblox_color",
                "has_rgb": True,
                "point_count": 1,
            }
        ),
        encoding="utf-8",
    )


def _write_mid360_chunk(flight_dir: Path, sequence: int = 1) -> None:
    payload = struct.pack("<ffffff", 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    chunk_id = f"mid360_{sequence:06d}"
    (flight_dir / f"{chunk_id}-feedfacefeedface.xyz32").write_bytes(payload)
    meta = {
        "source": "mid360_raw",
        "layer": "mid360_lidar",
        "layer_type": "mid360_lidar",
        "has_rgb": False,
        "point_count": 2,
        "encoding": "xyz32_v1",
    }
    (flight_dir / f"{chunk_id}-feedfacefeedface.meta.json").write_text(
        json.dumps(meta),
        encoding="utf-8",
    )


def _write_esdf_chunk(flight_dir: Path, sequence: int = 1) -> None:
    payload = struct.pack("<ffffff", -1.0, -1.0, 0.1, 1.0, 1.0, 0.1)
    payload += bytes([0, 0, 0, 0, 0, 0])
    chunk_id = f"nvblox_esdf_{sequence:08d}"
    (flight_dir / f"{chunk_id}-abc123abc123abcd.xyzrgb32").write_bytes(payload)
    meta = {
        "source": "nvblox_esdf",
        "layer": "nvblox_esdf",
        "layer_type": "nvblox_esdf",
        "has_rgb": False,
        "point_count": 2,
        "encoding": "xyzrgb32_v1",
        "bbox_local_m": [-1.0, -1.0, 0.1, 1.0, 1.0, 0.1],
    }
    (flight_dir / f"{chunk_id}-abc123abc123abcd.meta.json").write_text(
        json.dumps(meta),
        encoding="utf-8",
    )


def _write_rack_face_rgbd_chunk(
    flight_dir: Path,
    *,
    face_id: str,
    points: int,
    has_rgb: bool = True,
    viewing_angle_deg: float = 30.0,
) -> None:
    chunk_id = f"rgbd_{face_id}_000001"
    payload = struct.pack("<ffffff", 1.0, 2.0, 1.5, 1.0, 2.5, 1.5)
    payload += bytes([255, 0, 0, 255, 0, 0])
    (flight_dir / f"{chunk_id}-facefacefaceface.xyzrgb32").write_bytes(payload)
    meta = {
        "source": "rgbd_colored",
        "layer": "rgbd_colored",
        "has_rgb": has_rgb,
        "point_count": points,
        "encoding": "xyzrgb32_v1",
        "bbox_local_m": [0.0, 0.0, 0.0, 2.0, 0.2, 2.0],
        "rack_face_id": face_id,
        "rack_face_center": [1.0, 0.1, 1.2],
        "rack_face_normal": [0.0, -1.0, 0.0],
        "viewing_angle_deg": viewing_angle_deg,
    }
    (flight_dir / f"{chunk_id}-facefacefaceface.meta.json").write_text(
        json.dumps(meta),
        encoding="utf-8",
    )


def test_manifest_counts_rgbd_and_raw_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_manifest_mix"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rgbd_chunk(flight_dir)
    _write_mid360_chunk(flight_dir)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)
    assert manifest.rgbd_colored_available is True
    assert manifest.raw_lidar_only is False
    assert manifest.chunk_counts["rgbd_colored"] == 1
    assert manifest.chunk_counts["mid360_raw"] == 1


def test_manifest_reconciles_missing_topic_when_chunks_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_esdf_reconciled"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_esdf_chunk(flight_dir)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(live_map_manifest, "warehouse_live_map_chunk_storage", storage)

    manifest = live_map_manifest.build_manifest_from_flight_dir(
        flight_id,
        missing_topics=["/nvblox_node/static_esdf_pointcloud"],
    )

    assert manifest.chunk_counts["nvblox_esdf"] == 1
    assert "/nvblox_node/static_esdf_pointcloud" not in manifest.missing_topics
    assert manifest.source_quality["nvblox_esdf"]["floor_area_m2"] == 4.0


def test_manifest_builds_rack_face_coverage_and_repair_waypoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_rack_face_coverage"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rack_face_rgbd_chunk(flight_dir, face_id="A-01-L", points=10)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(live_map_manifest, "warehouse_live_map_chunk_storage", storage)

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)

    assert manifest.chunk_quality[0]["rack_face_id"] == "A-01-L"
    coverage = manifest.rack_face_coverage
    assert coverage["face_count"] == 1
    assert coverage["uncovered_face_count"] == 1
    assert coverage["faces"][0]["reasons"] == ["low_point_density", "missing_esdf"]
    repair = manifest.coverage_repair
    assert repair["uncovered_rack_faces"] == ["A-01-L"]
    assert repair["extra_pass_waypoints"][0]["pose_local_m"]["y"] < 0.0
    assert repair["extra_pass_waypoints"][0]["pose_local_m"]["frame_id"] == "warehouse_map"
    assert repair["extra_pass_waypoints"][0]["reasons"] == ["low_point_density", "missing_esdf"]


def test_validate_save_quality_fails_for_raw_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_raw_only"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_mid360_chunk(flight_dir)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        storage,
    )
    monkeypatch.setattr(live_map_manifest, "require_rgb_for_save", lambda: True)

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)
    ok, detail = live_map_manifest.validate_save_quality(manifest)
    assert ok is False
    assert "raw Mid360" in detail
    assert manifest.map_quality == "degraded_raw_only"


def test_manifest_quality_evidence_for_rgbd_with_has_rgb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_rgbd_quality"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rgbd_chunk(flight_dir)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    manifest = live_map_manifest.build_manifest_from_flight_dir(
        flight_id,
        localization_ok=False,
    )
    assert manifest.rgbd_colored_available is True
    assert manifest.rgbd_has_rgb is True
    assert manifest.map_quality == "rgbd_colored"
    assert manifest.default_view_layer == "rgbd_colored"
    assert manifest.quality_evidence is True
    assert manifest.localization_quality == "degraded"
    ok, _detail = live_map_manifest.validate_save_quality(manifest)
    assert ok is True


def test_manifest_labels_rgbd_geometry_without_color_honestly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_rgbd_xyz"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rgbd_chunk(flight_dir, has_rgb=False)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        WarehouseLiveMapChunkStorage(root=tmp_path),
    )

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)

    assert manifest.rgbd_cloud_available is True
    assert manifest.rgbd_colored_available is False
    assert manifest.rgbd_has_rgb is False
    assert manifest.map_quality == "rgbd_xyz_uncolored"
    assert manifest.default_view_layer == "rgbd_xyz_uncolored"
    assert manifest.chunk_counts["rgbd_xyz_uncolored"] == 1


def test_internal_nvblox_color_layer_is_diagnostic_not_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_internal_nvblox_only"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_internal_nvblox_color_chunk(flight_dir)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        WarehouseLiveMapChunkStorage(root=tmp_path),
    )

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)

    assert manifest.default_view_layer is None
    assert manifest.map_quality == "empty"
    assert manifest.diagnostic_nvblox_layers == ["nvblox_color"]


def test_validate_manifest_chunk_files_reports_missing_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_partial_manifest"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rgbd_chunk(flight_dir, sequence=1)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    missing, total = live_map_manifest.validate_manifest_chunk_files(
        flight_id,
        chunk_ids=["rgbd_000001", "rgbd_000002"],
    )
    assert missing == ["rgbd_000002"]
    assert total > 0

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)
    manifest.missing_chunks = missing
    manifest.manifest_status = "partial"
    ok, detail = live_map_manifest.validate_save_quality(manifest)
    assert ok is False
    assert "partial" in detail


def test_finalize_manifest_integrity_complete_when_all_chunks_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_complete_manifest"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rgbd_chunk(flight_dir, sequence=1)
    _write_rgbd_chunk(flight_dir, sequence=2)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)
    finalized = live_map_manifest.finalize_manifest_integrity(manifest)
    assert finalized.manifest_status == "complete"
    assert finalized.missing_chunks == []
    assert finalized.total_bytes > 0


def test_save_and_load_manifest_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight_id = "flight_manifest_roundtrip"
    flight_dir = tmp_path / flight_id
    flight_dir.mkdir()
    _write_rgbd_chunk(flight_dir)

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(
        live_map_manifest,
        "warehouse_live_map_chunk_storage",
        storage,
    )

    manifest = live_map_manifest.build_manifest_from_flight_dir(flight_id)
    live_map_manifest.save_flight_manifest(manifest)
    loaded = live_map_manifest.load_flight_manifest(flight_id)
    assert loaded is not None
    assert loaded.rgbd_colored_available is True
    assert loaded.chunk_counts["rgbd_colored"] == 1


def test_warehouse_capture_finalize_does_not_wait_for_photogrammetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.modules.warehouse.service import capture

    monkeypatch.setattr(capture.settings, "warehouse_drone_sync_dir", str(tmp_path))
    monkeypatch.setattr(capture.settings, "warehouse_drone_capture_staging_dir", "")
    monkeypatch.setattr(capture.settings, "warehouse_capture_sync_cmd", "")
    monkeypatch.setattr(capture.settings, "warehouse_capture_sync_timeout_s", 30.0)
    monkeypatch.setattr(capture.settings, "warehouse_capture_sync_poll_s", 1.0)
    monkeypatch.setattr(capture.settings, "warehouse_capture_sync_min_files", 1)

    service = WarehouseCaptureSessionService()
    session = service.start_session(flight_id=73)
    started = time.monotonic()
    result = service.finalize_session(session, min_files=1, timeout_s=30.0)

    assert time.monotonic() - started < 1.0
    assert result["status"] == "ready"
    assert result["file_count"] >= 1
    assert (session.session_dir / "capture_session.json").exists()


@pytest.mark.asyncio
async def test_live_map_storage_skips_duplicate_chunk_rewrite(tmp_path: Path) -> None:
    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    payload = b"xyz"

    first = await storage.save_upload(
        flight_id="flight",
        chunk_id="rgbd_000001",
        frame_id="odom",
        kind="point_cloud",
        upload=_MemoryUpload(payload),
    )
    first_mtime = first.path.stat().st_mtime_ns
    time.sleep(0.001)
    second = await storage.save_upload(
        flight_id="flight",
        chunk_id="rgbd_000001",
        frame_id="odom",
        kind="point_cloud",
        upload=_MemoryUpload(payload),
    )

    assert second.path == first.path
    assert second.path.stat().st_mtime_ns == first_mtime


def test_live_map_storage_skips_duplicate_metadata_rewrite(tmp_path: Path) -> None:
    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    metadata: dict[str, Any] = {"source": "rgbd_colored", "sequence": 1}

    path = storage.save_chunk_metadata(
        flight_id="flight",
        chunk_id="rgbd_000001",
        checksum_sha256="a" * 64,
        metadata=metadata,
    )
    first_mtime = path.stat().st_mtime_ns
    time.sleep(0.001)
    second = storage.save_chunk_metadata(
        flight_id="flight",
        chunk_id="rgbd_000001",
        checksum_sha256="a" * 64,
        metadata=dict(metadata),
    )

    assert second == path
    assert path.stat().st_mtime_ns == first_mtime

from pathlib import Path
from types import SimpleNamespace

from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseShelf,
)
from backend.modules.warehouse.service import structure_jobs
from backend.modules.warehouse.service.layout import can_auto_publish_layout
from backend.modules.warehouse.service.live_map_storage import WarehouseLiveMapChunkStorage


def test_artifact_lineage_is_deterministic_and_content_addressed(
    tmp_path: Path, monkeypatch
) -> None:
    storage = WarehouseLiveMapChunkStorage(tmp_path)
    monkeypatch.setattr(structure_jobs, "warehouse_live_map_chunk_storage", storage)
    monkeypatch.setattr(structure_jobs, "load_flight_manifest", lambda _flight_id: None)
    flight = storage.flight_dir("flight-1")
    flight.mkdir(parents=True)
    source = flight / "cloud.bin"
    source.write_bytes(b"first")

    first, _, inputs = structure_jobs._scan_artifact_lineage(
        "flight-1", model_id=2, coordinate_frame_id=3, extraction_params={"voxel": 0.1}
    )
    same, _, _ = structure_jobs._scan_artifact_lineage(
        "flight-1", model_id=2, coordinate_frame_id=3, extraction_params={"voxel": 0.1}
    )
    source.write_bytes(b"second")
    changed, _, _ = structure_jobs._scan_artifact_lineage(
        "flight-1", model_id=2, coordinate_frame_id=3, extraction_params={"voxel": 0.1}
    )

    assert first == same
    assert first != changed
    assert inputs[0]["checksum_sha256"]


def test_confirmed_or_manual_layout_blocks_auto_publish() -> None:
    assert can_auto_publish_layout(None) is True
    assert can_auto_publish_layout(SimpleNamespace(provenance_status="auto")) is True
    assert can_auto_publish_layout(SimpleNamespace(provenance_status="manual")) is False
    assert can_auto_publish_layout(SimpleNamespace(provenance_status="confirmed")) is False


def test_lineage_columns_are_queryable() -> None:
    assert "checksum_sha256" in WarehouseScanArtifactSet.__table__.columns
    assert "artifact_set_id" in WarehouseLayoutVersion.__table__.columns
    assert "provenance_status" in WarehouseLayoutVersion.__table__.columns
    assert "confidence" in WarehouseLayoutVersion.__table__.columns
    assert "provenance_status" in WarehouseScanTarget.__table__.columns


def test_all_extraction_provenance_states_are_database_constrained() -> None:
    models = (
        WarehouseLayoutVersion,
        WarehouseAisle,
        WarehouseRack,
        WarehouseShelf,
        WarehouseBin,
        WarehouseScanTarget,
    )
    for model in models:
        constraint_names = {constraint.name for constraint in model.__table__.constraints}
        assert any(name and name.endswith("_provenance") for name in constraint_names)

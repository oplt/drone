from pathlib import Path
from types import SimpleNamespace

from backend.modules.warehouse.models import (
    WarehouseAisle,
    WarehouseBin,
    WarehouseLayoutVersion,
    WarehouseRack,
    WarehouseRackTemplate,
    WarehouseRackTemplateVersion,
    WarehouseSafetyZone,
    WarehouseScanArtifactSet,
    WarehouseScanTarget,
    WarehouseShelf,
)
from backend.modules.warehouse.service import structure_jobs
from backend.modules.warehouse.service.structure_extraction import StructureExtractionParams
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
    assert "scanner_metadata_json" in WarehouseScanTarget.__table__.columns
    assert "path_validation_json" in WarehouseScanTarget.__table__.columns
    assert "failure_reason" in WarehouseScanTarget.__table__.columns
    assert "warehouse_map_id" in WarehouseRackTemplate.__table__.columns
    assert "bay_width_m" in WarehouseRackTemplateVersion.__table__.columns
    assert "template_version_id" in WarehouseRack.__table__.columns
    assert "fitted_transform_json" in WarehouseRack.__table__.columns
    assert "template_fit_json" in WarehouseRack.__table__.columns
    for model in (
        WarehouseAisle,
        WarehouseRack,
        WarehouseShelf,
        WarehouseBin,
        WarehouseSafetyZone,
    ):
        assert "template_id" in model.__table__.columns
        assert "source_artifact_set_id" in model.__table__.columns
        assert "confidence_breakdown_json" in model.__table__.columns
        assert "fit_residual_m" in model.__table__.columns
        assert "observed_point_count" in model.__table__.columns
        assert "coverage_ratio" in model.__table__.columns
        assert "last_verified_at" in model.__table__.columns
    assert "face_plane_json" in WarehouseRack.__table__.columns
    assert "center_local_json" in WarehouseBin.__table__.columns
    assert "volume_json" in WarehouseBin.__table__.columns


def test_manifest_coverage_gate_rejects_missing_layers_and_tf_jumps(monkeypatch) -> None:
    manifest = SimpleNamespace(
        as_dict=lambda: {
            "point_counts": {"rgbd_colored": 2_000},
            "source_quality": {
                "rgbd_colored": {"floor_area_m2": 100.0, "points_per_m2": 20.0}
            },
            "chunk_counts": {"rgbd_colored": 1},
            "occupancy_available": False,
            "esdf_available": False,
            "rgbd_has_rgb": True,
            "tf_jump_back_count": 4,
        }
    )
    monkeypatch.setattr(structure_jobs, "load_flight_manifest", lambda _flight_id: manifest)
    monkeypatch.setattr(
        structure_jobs.settings,
        "warehouse_structure_min_surface_points_per_m2",
        5.0,
    )
    monkeypatch.setattr(structure_jobs.settings, "warehouse_structure_require_occupancy_grid", True)
    monkeypatch.setattr(
        structure_jobs.settings,
        "warehouse_structure_require_esdf_or_inflated_occupancy",
        True,
    )
    monkeypatch.setattr(structure_jobs.settings, "warehouse_structure_max_tf_jump_count", 2)

    try:
        structure_jobs._validate_manifest_coverage(
            "flight-coverage",
            StructureExtractionParams(min_surface_points=1_000),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("coverage gate did not reject invalid manifest")

    assert "occupancy grid present" in message
    assert "ESDF or inflated occupancy" in message
    assert "TF jump count 4" in message


def test_manifest_coverage_gate_requires_rgb_only_for_barcode(monkeypatch) -> None:
    manifest = SimpleNamespace(
        as_dict=lambda: {
            "point_counts": {"rgbd_xyz_uncolored": 2_000, "nvblox_occupancy": 100},
            "source_quality": {
                "rgbd_xyz_uncolored": {"floor_area_m2": 10.0, "points_per_m2": 200.0}
            },
            "chunk_counts": {"rgbd_xyz_uncolored": 1, "nvblox_occupancy": 1},
            "occupancy_available": True,
            "esdf_available": False,
            "rgbd_has_rgb": False,
            "tf_jump_back_count": 0,
        }
    )
    monkeypatch.setattr(structure_jobs, "load_flight_manifest", lambda _flight_id: manifest)
    monkeypatch.setattr(
        structure_jobs.settings,
        "warehouse_structure_min_surface_points_per_m2",
        5.0,
    )
    monkeypatch.setattr(structure_jobs.settings, "warehouse_structure_require_occupancy_grid", True)
    monkeypatch.setattr(
        structure_jobs.settings,
        "warehouse_structure_require_esdf_or_inflated_occupancy",
        True,
    )
    monkeypatch.setattr(
        structure_jobs.settings,
        "warehouse_structure_require_rgb_when_barcode_expected",
        True,
    )

    structure_jobs._validate_manifest_coverage(
        "flight-geometry",
        StructureExtractionParams(min_surface_points=1_000, barcode_scan_expected=False),
    )

    try:
        structure_jobs._validate_manifest_coverage(
            "flight-barcode",
            StructureExtractionParams(min_surface_points=1_000, barcode_scan_expected=True),
        )
    except RuntimeError as exc:
        assert "RGB-D/color present" in str(exc)
    else:
        raise AssertionError("barcode coverage gate did not require RGB")


def test_rack_template_assignment_snaps_bin_geometry() -> None:
    from backend.modules.warehouse.service.rack_templates import apply_template_to_rack_geometry

    rack = SimpleNamespace(
        id=10,
        geometry_json={},
        template_version_id=None,
        fitted_transform_json={},
        template_fit_json={},
    )
    shelf = SimpleNamespace(id=20, level=0, geometry_json={})
    bins = [
        SimpleNamespace(
            id=30,
            shelf_id=20,
            code="B1",
            geometry_json={
                "target_point": {
                    "frame_id": "warehouse_map",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "z_m": 0.5,
                }
            },
        ),
        SimpleNamespace(
            id=31,
            shelf_id=20,
            code="B2",
            geometry_json={
                "target_point": {
                    "frame_id": "warehouse_map",
                    "x_m": 1.0,
                    "y_m": 0.0,
                    "z_m": 0.5,
                }
            },
        ),
    ]
    template = SimpleNamespace(id=1, name="Selective rack", rack_type="selective")
    version = SimpleNamespace(
        id=2,
        version=3,
        bay_width_m=2.0,
        shelf_heights_json=[0.75],
        bin_pitch_m=0.5,
        bin_count=2,
        left_face_naming="left_to_right",
        right_face_naming="right_to_left",
        barcode_scan_side="front",
        preferred_standoff_m=1.2,
        min_scanner_angle_deg=20.0,
    )

    result = apply_template_to_rack_geometry(
        rack=rack,
        shelves=[shelf],
        bins_by_shelf={20: bins},
        template=template,
        version=version,
    )

    assert rack.template_version_id == 2
    assert rack.geometry_json["template"]["template_version_id"] == 2
    assert result["snapped_bin_count"] == 2
    assert bins[0].geometry_json["template"]["bin_pitch_m"] == 0.5
    assert bins[0].geometry_json["target_point"]["z_m"] == 0.75


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

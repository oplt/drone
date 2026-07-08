from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.modules.warehouse.schemas import (
    WarehouseInspectionResultPage,
    WarehouseScanTargetPage,
)
from backend.modules.warehouse.service import structure_jobs
from backend.modules.warehouse.service.drift_guard import transform_checksum


@pytest.mark.asyncio
async def test_warehouse_settings_access_uses_repository(monkeypatch) -> None:
    from backend.modules.warehouse import http_access

    repository = AsyncMock()
    repository.read_document.return_value = {"warehouse": {"mission_defaults": {"cruise_alt": 3.0}}}
    monkeypatch.setattr(http_access, "settings_repo", repository)

    settings = await http_access.read_warehouse_settings(AsyncMock())
    await http_access.write_warehouse_setting(
        AsyncMock(),
        key="exploration_profile",
        value={"speed_mps": 1.0},
    )

    assert settings == {"mission_defaults": {"cruise_alt": 3.0}}
    repository.write_document.assert_awaited_once()
    written = repository.write_document.await_args.kwargs["data"]
    assert written["warehouse"]["exploration_profile"] == {"speed_mps": 1.0}


def test_warehouse_scan_target_page_schema() -> None:
    page = WarehouseScanTargetPage(items=[], total=0, limit=200, offset=0)
    assert page.total == 0
    assert page.limit == 200


def test_layout_entity_dict_exposes_category9_metadata() -> None:
    from backend.modules.warehouse.routers.layouts import _entity_dict

    verified_at = datetime.now(UTC)
    row = SimpleNamespace(
        id=7,
        code="R1",
        geometry_json={"line": []},
        template_id=1,
        template_version_id=2,
        source_artifact_set_id=3,
        fitted_transform_json={"tx": 1.0},
        template_fit_json={"coverage_ratio": 0.8},
        face_plane_json={"normal": [1, 0, 0]},
        center_local_json={"x_m": 1.0},
        volume_json={"width_m": 0.5},
        confidence_breakdown_json={"geometry": 0.9},
        fit_residual_m=0.02,
        observed_point_count=44,
        coverage_ratio=0.8,
        last_verified_at=verified_at,
        active=True,
    )

    payload = _entity_dict(row)

    assert payload["geometry"] == {"line": []}
    assert payload["template_id"] == 1
    assert payload["template_version_id"] == 2
    assert payload["source_artifact_set_id"] == 3
    assert payload["face_plane_json"] == {"normal": [1, 0, 0]}
    assert payload["center_local_json"] == {"x_m": 1.0}
    assert payload["volume_json"] == {"width_m": 0.5}
    assert payload["confidence_breakdown_json"] == {"geometry": 0.9}
    assert payload["fit_residual_m"] == 0.02
    assert payload["observed_point_count"] == 44
    assert payload["coverage_ratio"] == 0.8
    assert payload["last_verified_at"] == verified_at


def test_candidate_metadata_promotion_applies_geometry_fields() -> None:
    from backend.modules.warehouse.routers.layout_candidates import _apply_candidate_metadata

    reviewed_at = datetime.now(UTC)
    candidate = SimpleNamespace(
        confidence=0.91,
        reviewed_at=reviewed_at,
        created_at=None,
        geometry_json={
            "template_id": 10,
            "template_version_id": 11,
            "source_artifact_set_id": 12,
            "template_fit": {"bay_width_residual_m": 0.03, "coverage_ratio": 0.7},
            "rack_face_plane": {"support_points": 88},
            "target_point": {"frame_id": "warehouse_map", "x_m": 1.0},
            "volume": {"depth_m": 0.6},
            "confidence_breakdown": {"template_fit": 0.9},
            "observed_point_count": 88,
            "coverage_ratio": 0.7,
        },
    )
    row = SimpleNamespace(
        confidence=None,
        confidence_breakdown_json={},
        template_id=None,
        template_version_id=None,
        source_artifact_set_id=None,
        fitted_transform_json={},
        template_fit_json={},
        face_plane_json={},
        center_local_json={},
        volume_json={},
        fit_residual_m=None,
        observed_point_count=None,
        coverage_ratio=None,
        last_verified_at=None,
    )

    _apply_candidate_metadata(row, candidate)

    assert row.confidence == 0.91
    assert row.template_id == 10
    assert row.template_version_id == 11
    assert row.source_artifact_set_id == 12
    assert row.template_fit_json["bay_width_residual_m"] == 0.03
    assert row.face_plane_json == {"support_points": 88}
    assert row.center_local_json["x_m"] == 1.0
    assert row.volume_json == {"depth_m": 0.6}
    assert row.confidence_breakdown_json == {"template_fit": 0.9}
    assert row.fit_residual_m == 0.03
    assert row.observed_point_count == 88
    assert row.coverage_ratio == 0.7
    assert row.last_verified_at == reviewed_at


def test_warehouse_inspection_result_page_schema() -> None:
    page = WarehouseInspectionResultPage(items=[], total=0, limit=200, offset=0)
    assert page.items == []
    assert page.offset == 0


def test_get_extraction_state_skips_celery_probe_when_recent() -> None:
    structure_jobs._EXTRACTION_STATE.clear()
    structure_jobs._EXTRACTION_CELERY_PROBE_AT.clear()
    structure_jobs._EXTRACTION_STATE[3] = {
        "status": "queued",
        "task_id": "task-123",
        "warehouse_map_id": 3,
    }
    structure_jobs._EXTRACTION_CELERY_PROBE_AT[3] = time.monotonic()

    with patch("celery.result.AsyncResult") as mock_result:
        state = structure_jobs.get_extraction_state(3)
        mock_result.assert_not_called()

    assert state is not None
    assert state["status"] == "queued"


def test_warehouse_mapping_worker_ready_uses_cache() -> None:
    structure_jobs._WORKER_READY_CACHE = (time.monotonic(), True, None)
    ready, detail = structure_jobs.warehouse_mapping_worker_ready()
    assert ready is True
    assert detail is None


def test_structure_failure_reason_codes_are_machine_readable() -> None:
    assert structure_jobs._failure_reason_codes_from_message(
        "Structure extraction requires a locked warehouse coordinate frame"
    ) == ["missing_locked_coordinate_frame"]
    assert structure_jobs._failure_reason_codes_from_message(
        "No surface point-cloud chunks found for flight 'abc'"
    ) == ["missing_surface_pointcloud"]
    assert structure_jobs._failure_reason_codes_from_message(
        "localization confidence must be in [0.7, 1.0]"
    ) == ["localization_confidence_low"]
    assert structure_jobs._failure_reason_codes_from_message(
        "Insufficient map coverage: 20 surface points after voxel downsample, minimum=1000."
    ) == ["insufficient_map_coverage"]


def test_structure_extraction_coordinate_frame_must_be_trusted() -> None:
    transform = {
        "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    }
    base = {
        "transform_json": transform,
        "transform_timestamp": datetime.now(UTC),
        "max_age_s": 60.0,
    }
    covariance = [0.0] * 36
    covariance[0] = covariance[7] = covariance[14] = 0.01

    with pytest.raises(RuntimeError, match="non-placeholder"):
        structure_jobs._validate_extraction_coordinate_frame(
            SimpleNamespace(
                **base,
                covariance_json=covariance,
                transform_checksum="0" * 64,
                confidence=0.95,
            )
        )

    with pytest.raises(RuntimeError, match="localization confidence"):
        structure_jobs._validate_extraction_coordinate_frame(
            SimpleNamespace(
                **base,
                covariance_json=covariance,
                transform_checksum=transform_checksum(transform),
                confidence=0.69,
            )
        )

    with pytest.raises(RuntimeError, match="non-placeholder coordinate covariance"):
        structure_jobs._validate_extraction_coordinate_frame(
            SimpleNamespace(
                **base,
                covariance_json=[0.0] * 36,
                transform_checksum=transform_checksum(transform),
                confidence=0.9,
            )
        )

    structure_jobs._validate_extraction_coordinate_frame(
        SimpleNamespace(
            **base,
            covariance_json=covariance,
            transform_checksum=transform_checksum(transform),
            confidence=0.7,
        )
    )


def test_structure_extraction_demotes_active_targets_without_clearance_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.modules.warehouse.service.structure_extraction import (
        GeneratedTarget,
        StructureResult,
    )

    monkeypatch.setattr(
        structure_jobs.settings, "warehouse_structure_require_clearance_evidence", True
    )
    target = GeneratedTarget(
        aisle_code="A1",
        rack_code="R1",
        shelf_level=0,
        bin_code="B1",
        target_point={"frame_id": "warehouse_map", "x_m": 1.0, "y_m": 2.0, "z_m": 1.5},
        shelf_normal={"frame_id": "warehouse_map", "x": 1.0, "y": 0.0, "z": 0.0},
        scan_pose={"frame_id": "warehouse_map", "x_m": 0.0, "y_m": 2.0, "z_m": 1.5},
        standoff_m=1.2,
        priority=1,
        clearance_status="active",
        clearance_m=2.0,
        clearance_source="point_cloud_kdtree",
    )
    result = StructureResult(
        targets=[target],
        summary={
            "counts": {"aisles": 1, "racks": 1, "targets": 1, "active_targets": 1},
            "target_counts": {"candidate": 1, "active": 1, "needs_review": 0, "rejected": 0},
            "clearance": {"source": "point_cloud_kdtree"},
        },
    )

    structure_jobs._force_review_without_clearance_evidence(result)

    assert target.clearance_status == "needs_review"
    assert result.summary["target_counts"]["active"] == 0
    assert result.summary["target_counts"]["needs_review"] == 1
    assert result.summary["coordinate_setup_status"] == "draft"


@pytest.mark.asyncio
async def test_landmark_frame_validation_uses_dock_marker_observations() -> None:
    transform = {
        "translation": {"x": 1.0, "y": 2.0, "z": 0.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    }
    dock = SimpleNamespace(
        id=1,
        name="Dock",
        marker_id="tag-1",
        pose_local_json={"x_m": 2.0, "y_m": 4.0, "z_m": 0.0},
        meta_data={"marker_observation_odom": {"x_m": 1.0, "y_m": 2.0, "z_m": 0.0}},
    )

    class _Scalars:
        def all(self):
            return [dock]

    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=_Scalars)))

    result = await structure_jobs._validate_landmark_frame(
        db,
        warehouse_map_id=1,
        coordinate_frame=SimpleNamespace(transform_json=transform),
    )

    assert result["status"] == "passed"
    assert result["configured_landmarks"] == 1
    assert result["observed_landmarks"] == 1


def test_structure_debug_artifact_is_downloadable_json(tmp_path, monkeypatch) -> None:
    from backend.modules.warehouse.service.live_map_storage import WarehouseLiveMapChunkStorage

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(structure_jobs, "warehouse_live_map_chunk_storage", storage)

    path, url = structure_jobs._write_debug_artifact(
        "flight-1",
        payload={"failure_reason_codes": ["missing_occupancy_grid"]},
        lineage_checksum="a" * 64,
    )

    assert path is not None
    assert path.exists()
    assert path.suffix == ".json"
    assert url == "/warehouse/live-map/flight-1/chunks/structure_debug-aaaaaaaaaaaaaaaa/download"


def test_structure_debug_payload_contains_extraction_evidence() -> None:
    from backend.modules.warehouse.service.structure_extraction import StructureResult

    result = StructureResult(
        summary={
            "status": "needs_review",
            "frame_id": "warehouse_map",
            "floor_z": 0.02,
            "axis_deg": 90.0,
            "height_band_m": [0.2, 2.8],
            "map_quality": {
                "chunk_counts": {"rgbd_colored": 2, "nvblox_esdf": 1},
                "point_counts": {"rgbd_colored": 10_000},
            },
            "aisle_graph": {"nodes": [], "edges": []},
            "rack_plane_clusters": [{"v_m": 1.0, "support_points": 50}],
            "racks": [
                {
                    "code": "R1",
                    "shelf_detection": {
                        "source": "horizontal_plane_histogram",
                        "levels_m": [0.8, 1.6],
                        "confidence_breakdown": {"peak_support": 0.9},
                    },
                    "confidence_breakdown": {"geometry": 0.8},
                }
            ],
            "candidate_targets": [
                {
                    "candidate_id": "R1:A1:B1:L0",
                    "confidence_breakdown": {"clearance": 0.6},
                }
            ],
            "rejection_diagnostics": [{"candidate_id": "R1:A1:B1:L0"}],
            "quality": {"confidence": 0.7},
        }
    )

    payload = structure_jobs._debug_payload(
        warehouse_map_id=1,
        model_id=2,
        client_flight_id="flight-1",
        coordinate_frame_id=3,
        result=result,
        lineage_checksum="b" * 64,
        manifest_json={"chunk_counts": {"rgbd_colored": 2}},
        inputs_json=[{"source_quality": {"source": "rgbd_colored"}}],
    )

    assert payload["input_chunk_counts"] == {"rgbd_colored": 2, "nvblox_esdf": 1}
    assert payload["source_layers_used"] == ["rgbd_colored"]
    assert payload["floor_plane"]["z_m"] == 0.02
    assert payload["detected_aisle_axis"]["axis_deg"] == 90.0
    assert payload["rack_plane_clusters"][0]["support_points"] == 50
    assert payload["shelf_histogram_peaks"][0]["levels_m"] == [0.8, 1.6]
    assert payload["rejected_target_diagnostics"][0]["candidate_id"] == "R1:A1:B1:L0"
    assert payload["confidence_breakdown"]["targets"][0]["clearance"] == 0.6


def test_category8_prometheus_metrics_exist() -> None:
    from backend.observability import prometheus_metrics

    assert prometheus_metrics.warehouse_structure_extraction_failures_total
    assert prometheus_metrics.warehouse_low_confidence_candidates_total
    assert prometheus_metrics.warehouse_layout_publish_blocks_total
    assert prometheus_metrics.warehouse_inspection_target_clearance_failures_total


def test_structure_quality_summary_exposes_failure_reason_codes() -> None:
    summary = {
        "counts": {"aisles": 0, "racks": 0, "candidate_targets": 0},
        "clearance": {"source": "point_cloud_fallback"},
        "map_quality": {"missing_topics": ["/nvblox_node/static_esdf_pointcloud"]},
    }

    structure_jobs.ensure_structure_quality_summary(summary)

    quality = summary["quality"]
    assert quality["status"] == "needs_review"
    assert "insufficient_detected_structure" in quality["failure_reason_codes"]
    assert "missing_occupancy_grid" in quality["failure_reason_codes"]


def test_structure_quality_summary_includes_rack_face_coverage_repair() -> None:
    summary = {
        "counts": {"aisles": 1, "racks": 1, "candidate_targets": 2, "active_targets": 0},
        "clearance": {"source": "occupancy_grid"},
        "map_quality": {
            "chunk_counts": {"nvblox_occupancy": 1},
            "rack_face_coverage": {
                "face_count": 2,
                "covered_face_count": 1,
                "uncovered_face_count": 1,
                "coverage_ratio": 0.5,
            },
            "coverage_repair": {
                "uncovered_rack_faces": ["A-01-L"],
                "extra_pass_waypoints": [{"rack_face_id": "A-01-L"}],
            },
        },
    }

    structure_jobs.ensure_structure_quality_summary(summary)

    quality = summary["quality"]
    assert "rack_face_coverage_incomplete" in quality["failure_reason_codes"]
    assert quality["rack_face_coverage"]["coverage_ratio"] == 0.5
    assert quality["coverage_repair"]["uncovered_rack_faces"] == ["A-01-L"]


def test_structure_quality_summary_includes_landmark_accuracy_reasons() -> None:
    summary = {
        "counts": {"aisles": 1, "racks": 1, "candidate_targets": 1, "active_targets": 0},
        "clearance": {"source": "point_cloud_fallback"},
        "landmark_frame_validation": {"status": "missing_observations"},
    }

    structure_jobs.ensure_structure_quality_summary(summary)

    assert "missing_landmark_observations" in summary["quality"]["failure_reason_codes"]


def test_preflight_snapshot_cache_helpers() -> None:
    import asyncio

    from backend.modules.warehouse import api as warehouse_api
    from backend.modules.warehouse.service import preflight_cache

    preflight_cache._PREFLIGHT_SNAPSHOT_CACHE.clear()
    user_id = 42
    snapshot = warehouse_api.WarehousePreflightOut(
        primary_blocker="test",
        blockers=["test"],
        blocking_reasons=["test"],
    )

    async def _run() -> None:
        await preflight_cache.store_preflight_snapshot_cache(user_id, False, snapshot)
        cached = await preflight_cache.get_cached_preflight_snapshot(user_id, False)
        assert cached is not None
        assert cached.primary_blocker == "test"

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_structure_summary_endpoint_has_no_quality_helper_name_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.modules.warehouse.routers import structure

    asset = SimpleNamespace(
        model_id=12,
        meta_data={
            "target_count": 0,
            "summary": {
                "counts": {"aisles": 1, "racks": 1, "targets": 0},
                "clearance": {"source": "point_cloud_kdtree"},
            },
        },
    )
    scalar_result = SimpleNamespace(scalar_one_or_none=lambda: asset)
    db = SimpleNamespace(execute=AsyncMock(return_value=scalar_result))
    monkeypatch.setattr(structure, "get_map_or_404", AsyncMock(return_value=object()))

    response = await structure.get_warehouse_structure(
        warehouse_map_id=3,
        db=db,
        org_user=SimpleNamespace(user=object()),
    )

    assert response.warehouse_map_id == 3
    assert response.summary["quality"]["status"] == "needs_review"


def test_structure_extraction_degrades_when_all_clearance_candidates_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from backend.modules.warehouse.service import structure_extraction as extraction

    calls = 0

    def density_bands(*_args, occupied: bool, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [extraction._Band(-0.25, 0.25)]
        if calls == 2:
            return [extraction._Band(0.75, 1.75)]
        assert occupied is True
        return [extraction._Band(-1.0, 1.0)]

    def reject_all(*, result, params, rack_code, **_kwargs):
        result.rejected_clearance += 1
        result.rejection_diagnostics.append(
            {
                "candidate_id": f"{rack_code}:A1:B1:L0",
                "rejection_reason": "clearance_below_required",
                "clearance_m": 0.2,
                "required_clearance_m": params.required_clearance_m,
                "bbox": [0, 0, 0, 1, 1, 1],
                "frame_id": "warehouse_map",
            }
        )

    monkeypatch.setattr(extraction, "_detect_floor_z", lambda *_args: 0.0)
    monkeypatch.setattr(extraction, "_dominant_axis_rad", lambda *_args: 0.0)
    monkeypatch.setattr(extraction, "_density_bands", density_bands)
    monkeypatch.setattr(extraction, "_detect_shelf_levels", lambda *_args, **_kwargs: [1.0])
    monkeypatch.setattr(extraction, "_emit_bay_targets", reject_all)
    cloud = np.column_stack(
        (
            np.linspace(-1.0, 1.0, 100),
            np.zeros(100),
            np.linspace(0.5, 1.5, 100),
        )
    ).astype(np.float32)

    result = extraction.extract_structure(
        cloud,
        params=extraction.StructureExtractionParams(),
    )

    assert result.targets == []
    assert result.summary["status"] == "degraded"
    assert result.summary["racks"]
    assert result.summary["warnings"] == [
        "Structure detected but all scan targets failed the clearance gate."
    ]
    assert result.summary["rejection_diagnostics"][0]["candidate_id"]

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.modules.warehouse.schemas import (
    WarehouseInspectionResultPage,
    WarehouseScanTargetPage,
)
from backend.modules.warehouse.service import structure_jobs


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

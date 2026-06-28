import asyncio
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.modules.warehouse.models import (
    WarehouseInspectionMission,
    WarehouseInspectionResult,
    WarehouseScanTarget,
)
from backend.modules.warehouse.routers import scan_targets as api
from backend.modules.warehouse.schemas import (
    WarehouseInspectionMissionCreate,
    WarehouseScanPoseComputeIn,
    WarehouseScanTargetCreate,
    WarehouseScanTargetUpdate,
)
from backend.modules.warehouse.service.layout import BinContext
from backend.modules.warehouse.service.mission_revisions import MissionRevisionPins

NOW = datetime.now(UTC)


def _target(*, target_id: int = 1, frame_id: int = 42) -> WarehouseScanTarget:
    return WarehouseScanTarget(
        id=target_id,
        warehouse_map_id=7,
        coordinate_frame_id=frame_id,
        aisle_code="A1",
        barcode="ABC",
        target_point_local_json={
            "frame_id": "warehouse_map",
            "x_m": 2.0,
            "y_m": 3.0,
            "z_m": 1.5,
        },
        scan_pose_local_json={
            "frame_id": "warehouse_map",
            "x_m": 1.0,
            "y_m": 3.0,
            "z_m": 1.5,
            "yaw_deg": 0.0,
        },
        standoff_m=1.0,
        hover_time_s=1.0,
        scan_timeout_s=2.0,
        priority=10,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _payload() -> WarehouseScanTargetCreate:
    return WarehouseScanTargetCreate.model_validate(
        {
            "aisle_code": "A1",
            "barcode": "ABC",
            "target_point_local_json": {"x_m": 2, "y_m": 3, "z_m": 1.5},
            "scan_pose_local_json": {"x_m": 1, "y_m": 3, "z_m": 1.5},
        }
    )


def _patch_dependencies(monkeypatch) -> None:
    async def allow_map(*args, **kwargs):
        return object()

    async def locked_frame(*args, **kwargs):
        return SimpleNamespace(
            id=42,
            version=3,
            transform_json={
                "translation": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            },
        )

    monkeypatch.setattr(api, "get_map_or_404", allow_map)
    monkeypatch.setattr(api, "get_locked_coordinate_frame", locked_frame)

    async def bin_context(*args, **kwargs):
        return BinContext(9, 42, 3, "A1", "R1", 1, "B1")

    monkeypatch.setattr(api, "resolve_bin_context", bin_context)

    async def revision_pins(*args, **kwargs):
        return MissionRevisionPins(8, 2, 6, 4, 5, {"10": "a" * 64})

    async def verify_pins(*args, **kwargs):
        return None

    monkeypatch.setattr(api, "create_mission_revision_pins", revision_pins)
    monkeypatch.setattr(api, "verify_mission_revision_pins", verify_pins)


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


def test_create_uses_canonical_scan_pose_model_field(monkeypatch) -> None:
    _patch_dependencies(monkeypatch)
    db = _db()

    def add(row):
        row.id = 1
        row.created_at = NOW
        row.updated_at = NOW

    db.add.side_effect = add
    result = asyncio.run(
        api.create_warehouse_scan_target(
            warehouse_map_id=7,
            payload=_payload(),
            db=db,
            org_user=MagicMock(user=object()),
        )
    )
    row = db.add.call_args.args[0]
    assert row.scan_pose_local_json["x_m"] == 1.0
    assert not hasattr(row, "scanpose_local_json")
    assert result.scan_pose_local_json.x_m == 1.0


def test_create_rejects_stale_displayed_coordinate_revision(monkeypatch) -> None:
    _patch_dependencies(monkeypatch)
    db = _db()
    payload = _payload().model_copy(update={"coordinate_frame_id": 41})
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            api.create_warehouse_scan_target(
                warehouse_map_id=7,
                payload=payload,
                db=db,
                org_user=MagicMock(user=object()),
            )
        )
    assert error.value.status_code == 409
    db.add.assert_not_called()


def test_patch_updates_canonical_scan_pose_model_field(monkeypatch) -> None:
    _patch_dependencies(monkeypatch)
    row = _target()

    async def get_target(*args, **kwargs):
        return row

    monkeypatch.setattr(api, "get_scan_target_or_404", get_target)
    db = _db()
    payload = WarehouseScanTargetUpdate.model_validate(
        {"scan_pose_local_json": {"x_m": 0.5, "y_m": 3, "z_m": 1.5}}
    )
    result = asyncio.run(
        api.update_warehouse_scan_target(
            warehouse_map_id=7,
            target_id=1,
            payload=payload,
            db=db,
            org_user=MagicMock(user=object()),
        )
    )
    assert row.scan_pose_local_json["x_m"] == 0.5
    assert result.scan_pose_local_json.x_m == 0.5


def test_compute_pose_uses_canonical_service_and_response_names() -> None:
    payload = WarehouseScanPoseComputeIn.model_validate(
        {
            "target_point": {"x_m": 2, "y_m": 3, "z_m": 1.5},
            "shelf_normal": {"x": 1, "y": 0, "z": 0},
            "standoff_m": 1,
        }
    )
    result = asyncio.run(api.compute_warehouse_scan_pose(payload, MagicMock()))
    assert result.scan_pose.x_m == 1.0
    assert result.scan_pose.y_m == 3.0


def test_mission_creation_serializes_canonical_scan_pose(monkeypatch) -> None:
    _patch_dependencies(monkeypatch)
    target = _target()
    db = _db()
    query_result = MagicMock()
    query_result.scalars.return_value.all.return_value = [target]
    db.execute = AsyncMock(return_value=query_result)

    def add(row):
        row.id = 9
        row.created_at = NOW
        row.updated_at = NOW

    db.add.side_effect = add
    result = asyncio.run(
        api.create_warehouse_inspection_mission(
            payload=WarehouseInspectionMissionCreate(
                warehouse_map_id=7, target_ids=[1], name="Regression"
            ),
            db=db,
            org_user=MagicMock(user=object()),
        )
    )
    mission = db.add.call_args.args[0]
    assert mission.plan_json["waypoints"][0]["pose"]["x_m"] == 1.0
    assert mission.approval_status == "pending"
    assert len(mission.plan_checksum) == 64
    assert result.waypoints[0].pose.x_m == 1.0


def test_mock_run_persists_canonical_drone_pose_field(monkeypatch) -> None:
    _patch_dependencies(monkeypatch)
    target = _target()
    mission = WarehouseInspectionMission(
        id=9,
        warehouse_map_id=7,
        coordinate_frame_id=42,
        layout_version_id=8,
        map_model_id=6,
        validation_result_id=5,
        artifact_checksums_json={"10": "a" * 64},
        name="Regression",
        status="planned",
        scan_mode="barcode",
        return_to_dock=True,
        target_ids_json=[1],
        plan_json={},
        plan_checksum=hashlib.sha256(b"{}").hexdigest(),
        approval_status="approved",
        created_at=NOW,
        updated_at=NOW,
    )
    mission_result = MagicMock()
    mission_result.scalar_one_or_none.return_value = mission
    targets_result = MagicMock()
    targets_result.scalars.return_value.all.return_value = [target]
    db = _db()
    db.execute = AsyncMock(side_effect=[mission_result, targets_result])

    def add(row):
        if isinstance(row, WarehouseInspectionResult):
            row.id = 11
            row.scanned_at = NOW

    db.add.side_effect = add
    results = asyncio.run(
        api.run_warehouse_inspection_mission_mock(
            mission_id=9,
            db=db,
            org_user=MagicMock(user=object()),
        )
    )
    persisted = db.add.call_args.args[0]
    assert persisted.drone_pose_local_json["x_m"] == 1.0
    assert results[0].drone_pose_local_json.x_m == 1.0

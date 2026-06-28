import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.routers.scan_targets import import_warehouse_scan_targets
from backend.modules.warehouse.schemas import WarehouseScanTargetImport
from backend.modules.warehouse.service.frame_imports import normalize_scan_target_import
from backend.modules.warehouse.service.layout import BinContext


def _target(aisle_code: str) -> dict[str, object]:
    return {
        "aisle_code": aisle_code,
        "target_point_local_json": {"x_m": 1, "y_m": 2, "z_m": 3},
        "scan_pose_local_json": {"x_m": 1, "y_m": 1, "z_m": 3},
    }


def test_import_reloads_rows_with_one_query_and_preserves_input_order(monkeypatch) -> None:
    async def allow_map(*args, **kwargs) -> object:
        return object()

    monkeypatch.setattr(
        "backend.modules.warehouse.routers.scan_targets.get_map_or_404",
        allow_map,
    )

    async def locked_frame(*args, **kwargs) -> object:
        return MagicMock(id=42)

    monkeypatch.setattr(
        "backend.modules.warehouse.routers.scan_targets.get_locked_coordinate_frame",
        locked_frame,
    )

    async def bin_context(*args, **kwargs) -> BinContext:
        aisle = str(kwargs["aisle_code"])
        return BinContext(9, 42, 1 if aisle == "A" else 2, aisle, "R1", 1, "B1")

    monkeypatch.setattr(
        "backend.modules.warehouse.routers.scan_targets.resolve_bin_context",
        bin_context,
    )
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    now = datetime.now(UTC)
    added: list[WarehouseScanTarget] = []

    def add(row: WarehouseScanTarget) -> None:
        row.id = db.add.call_count
        row.created_at = now
        row.updated_at = now
        added.append(row)

    db.add.side_effect = add

    async def execute(statement) -> MagicMock:
        result = MagicMock()
        result.scalars.return_value.all.return_value = list(reversed(added))
        return result

    db.execute = AsyncMock(side_effect=execute)
    payload = WarehouseScanTargetImport(targets=[_target("A"), _target("B")])

    imported = asyncio.run(
        import_warehouse_scan_targets(
            warehouse_map_id=7,
            payload=payload,
            db=db,
            org_user=MagicMock(user=object()),
        )
    )

    assert [row.id for row in imported] == [1, 2]
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.execute.assert_awaited_once()
    db.refresh.assert_not_awaited()
    statement = db.execute.await_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True


def test_odom_import_is_explicitly_transformed_to_locked_warehouse_frame() -> None:
    target = normalize_scan_target_import(
        {
            **_target("A"),
            "target_point_local_json": {
                "frame_id": "odom",
                "x_m": 1,
                "y_m": 0,
                "z_m": 2,
            },
            "scan_pose_local_json": {
                "frame_id": "odom",
                "x_m": 0,
                "y_m": 0,
                "z_m": 2,
                "yaw_deg": 0,
            },
        },
        source_frame_id="odom",
        odom_to_warehouse_map_transform={
            "translation": {"x": 10, "y": 20, "z": 0},
            "rotation": {"x": 0, "y": 0, "z": 2**-0.5, "w": 2**-0.5},
        },
    )

    assert target.target_point_local_json.frame_id == "warehouse_map"
    assert target.target_point_local_json.x_m == pytest.approx(10)
    assert target.target_point_local_json.y_m == pytest.approx(21)
    assert target.scan_pose_local_json.yaw_deg == pytest.approx(90)


def test_import_rejects_undeclared_or_mixed_source_frames() -> None:
    with pytest.raises(ValueError, match="source_frame_id"):
        normalize_scan_target_import(
            {
                **_target("A"),
                "target_point_local_json": {
                    "frame_id": "foo",
                    "x_m": 1,
                    "y_m": 0,
                    "z_m": 2,
                },
            },
            source_frame_id="odom",
            odom_to_warehouse_map_transform={
                "translation": {"x": 0, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            },
        )

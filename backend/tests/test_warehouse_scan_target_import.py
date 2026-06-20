import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.routers.scan_targets import import_warehouse_scan_targets
from backend.modules.warehouse.schemas import WarehouseScanTargetImport


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

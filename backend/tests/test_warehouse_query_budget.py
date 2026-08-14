from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.warehouse.repository.maps import WarehouseMapMixin
from backend.modules.warehouse.routers import scan_targets


@pytest.mark.asyncio
async def test_list_warehouse_maps_issues_single_execute() -> None:
    mixin = WarehouseMapMixin()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )

    await mixin.list_warehouse_maps(db, owner_id=1)

    assert db.execute.await_count == 1


def test_list_warehouse_maps_eager_loads_hot_relations() -> None:
    source = inspect.getsource(WarehouseMapMixin.list_warehouse_maps)
    for relation in ("models", "docks", "coordinate_frames"):
        assert f"selectinload(WarehouseMap.{relation})" in source


@pytest.mark.asyncio
async def test_list_scan_targets_uses_count_and_page_queries_only(monkeypatch) -> None:
    execute_calls = 0

    async def counting_execute(_stmt):
        nonlocal execute_calls
        execute_calls += 1
        if execute_calls == 1:
            return MagicMock(scalar_one=MagicMock(return_value=0))
        return MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

    monkeypatch.setattr(scan_targets, "assert_map_or_404", AsyncMock())
    db = AsyncMock()
    db.execute = counting_execute
    response = MagicMock()
    org_user = MagicMock(user=MagicMock(id=1, org_id=1))

    await scan_targets.list_warehouse_scan_targets(
        warehouse_map_id=7,
        response=response,
        active=None,
        limit=50,
        offset=0,
        cursor=None,
        db=db,
        org_user=org_user,
    )

    assert execute_calls == 2

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.modules.warehouse.service.layout import (
    BinContext,
    LockedLayoutBinIndex,
    load_locked_layout_bin_index,
    resolve_bin_context_from_index,
)


@pytest.mark.asyncio
async def test_load_locked_layout_bin_index_builds_lookup_tables() -> None:
    layout = MagicMock(id=9, coordinate_frame_id=42)
    aisle = MagicMock(code="A")
    rack = MagicMock(code="R1")
    shelf = MagicMock(level=2)
    bin_a = MagicMock(id=101, code="B1")
    bin_b = MagicMock(id=102, code="B2")
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            all=MagicMock(
                return_value=[
                    (layout, aisle, rack, shelf, bin_a),
                    (layout, aisle, rack, shelf, bin_b),
                ]
            )
        )
    )

    index = await load_locked_layout_bin_index(db, warehouse_map_id=7)

    assert index.layout_version_id == 9
    assert index.coordinate_frame_id == 42
    assert resolve_bin_context_from_index(
        index,
        bin_id=101,
        aisle_code="A",
        rack_code="R1",
        shelf_level=2,
        bin_code="B1",
    ).bin_code == "B1"
    assert resolve_bin_context_from_index(
        index,
        bin_id=None,
        aisle_code="A",
        rack_code="R1",
        shelf_level=2,
        bin_code="B2",
    ).bin_id == 102


def test_resolve_bin_context_from_index_rejects_unknown_bin() -> None:
    index = LockedLayoutBinIndex(
        layout_version_id=1,
        coordinate_frame_id=2,
        by_bin_id={},
        by_identity={},
    )
    with pytest.raises(HTTPException) as exc:
        resolve_bin_context_from_index(
            index,
            bin_id=999,
            aisle_code="A",
            rack_code="R1",
            shelf_level=1,
            bin_code="B1",
        )
    assert exc.value.status_code == 409

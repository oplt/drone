from __future__ import annotations

from backend.modules.warehouse.repository.jobs import WAREHOUSE_SCANNED_MAP_PROCESSORS


def test_scanned_map_list_includes_manual_and_exploration_processors() -> None:
    assert "warehouse_scan" in WAREHOUSE_SCANNED_MAP_PROCESSORS
    assert "warehouse_manual_mapping" in WAREHOUSE_SCANNED_MAP_PROCESSORS
    assert "indoor_exploration" in WAREHOUSE_SCANNED_MAP_PROCESSORS
    assert "simulation" in WAREHOUSE_SCANNED_MAP_PROCESSORS

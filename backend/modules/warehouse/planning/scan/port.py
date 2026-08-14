from __future__ import annotations

from backend.modules.warehouse.ports import WarehousePerceptionPort


def build_warehouse_perception_port() -> WarehousePerceptionPort:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    return build_warehouse_perception_port()

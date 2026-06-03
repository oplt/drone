from __future__ import annotations

from backend.infrastructure.warehouse.mapping_stack_process import MappingStackStatus
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.mapping_stack_lifecycle import (
    _nvblox_ready_from_components,
    _readiness_from_status,
)


def _status(components: dict[str, object], *, ready: bool = False) -> WarehousePerceptionStatus:
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=ready,
        status="ready" if ready else "degraded",
        components=components,
    )


def test_strict_nvblox_rejects_warming_only() -> None:
    components = {
        "diagnostics_ready": True,
        "nvblox_healthy": True,
        "nvblox_warming_up": True,
        "nvblox_process_running": True,
        "listed_topics": ["/nvblox_node/static_esdf_pointcloud"],
    }
    assert _nvblox_ready_from_components(components, stack_running=True, strict=True) is False


def test_strict_nvblox_accepts_healthy_esdf() -> None:
    components = {
        "diagnostics_ready": True,
        "topic_matches": {
            "esdf": {
                "healthy": True,
                "matched": "/nvblox_node/static_esdf_pointcloud",
            }
        },
    }
    assert _nvblox_ready_from_components(components, stack_running=True, strict=True) is True


def test_loose_nvblox_accepts_warming() -> None:
    components = {
        "nvblox_warming_up": True,
        "nvblox_process_running": True,
    }
    assert _nvblox_ready_from_components(components, stack_running=True, strict=False) is True


def test_readiness_from_status_strict_blocks_false_ready() -> None:
    stack = MappingStackStatus(running=True, pid=1)
    status = _status(
        {
            "diagnostics_ready": True,
            "ros_graph": True,
            "nvblox_warming_up": True,
            "nvblox_process_running": True,
            "missing_nvblox_topics": [],
        }
    )
    result = _readiness_from_status(status, stack_status=stack, strict_nvblox=True)
    assert result.nvblox_ready is False
    assert "nvblox" in (result.detail or "").lower()

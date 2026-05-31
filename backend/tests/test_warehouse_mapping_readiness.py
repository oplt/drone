from __future__ import annotations

from backend.infrastructure.warehouse.mapping_stack_process import MappingStackStatus
from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.mapping_stack_lifecycle import (
    WarehouseMappingReadiness,
    _readiness_from_status,
    _suggested_actions,
)


def test_readiness_from_degraded_bridge_status() -> None:
    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=False,
        status="degraded",
        detail="Missing required topics: imu",
        components={
            "missing_required_topics": ["imu", "depth"],
            "missing_nvblox_topics": ["mesh"],
            "nvblox_healthy": False,
        },
    )
    stack = MappingStackStatus(running=True, pid=123)
    readiness = _readiness_from_status(status, stack_status=stack)

    assert readiness.bridge_reachable is True
    assert readiness.sensors_ready is False
    assert readiness.nvblox_ready is False
    assert readiness.missing_required == ("imu", "depth")
    assert readiness.missing_nvblox == ("mesh",)
    assert readiness.ready_for_preflight is False
    assert readiness.suggested_actions


def test_suggested_actions_for_idle_gazebo() -> None:
    actions = _suggested_actions(
        bridge_reachable=True,
        sensors_ready=False,
        nvblox_ready=False,
        missing_required=("rgb_image",),
        missing_nvblox=("mesh",),
        components={"ros_graph": True},
    )
    assert any("Gazebo" in action for action in actions)
    assert any("rgb_image" in action for action in actions)
    assert any("check_warehouse_ros_health" in action for action in actions)


def test_diagnostic_verify_actions_from_components() -> None:
    actions = _suggested_actions(
        bridge_reachable=True,
        sensors_ready=False,
        nvblox_ready=False,
        missing_required=("depth",),
        missing_nvblox=(),
        components={
            "ros_graph": True,
            "topic_diagnostics": {
                "depth": {
                    "healthy": False,
                    "expected": "/warehouse/front/rgbd/depth_image",
                    "matched": "/warehouse/front/rgbd/depth_image",
                    "error": "no publishers",
                }
            },
        },
    )
    assert any("ros2 topic info /warehouse/front/rgbd/depth_image" in action for action in actions)


def test_ready_for_preflight_requires_stack_sensors_and_nvblox() -> None:
    readiness = WarehouseMappingReadiness(
        stack_status=MappingStackStatus(running=True, pid=1),
        bridge_reachable=True,
        sensors_ready=True,
        nvblox_ready=True,
    )
    assert readiness.ready_for_preflight is True

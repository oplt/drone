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
    assert "imu" in readiness.missing_required
    assert "depth" in readiness.missing_required
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


def test_readiness_waits_when_bridge_diagnostics_not_ready() -> None:
    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=False,
        status="degraded",
        components={
            "diagnostics_ready": False,
            "probe_in_progress": True,
            "ros_graph": False,
        },
    )
    stack = MappingStackStatus(running=True, pid=123)
    readiness = _readiness_from_status(status, stack_status=stack)

    assert readiness.sensors_ready is False
    assert readiness.nvblox_ready is False
    assert "waiting for warehouse bridge diagnostics" in (readiness.detail or "")


def test_readiness_requires_live_takeoff_topics() -> None:
    import time

    from backend.modules.warehouse.ports import WarehousePerceptionStatus

    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components={
            "diagnostics_ready": True,
            "nvblox_healthy": True,
            "ros_graph": True,
            "missing_required_topics": [],
            "local_odometry_state": {"updated_at_monotonic": time.monotonic()},
            "topic_diagnostics": {
                "rgb_image": {"healthy": True, "listed": True},
                "depth": {"healthy": True, "listed": True},
                "imu": {"healthy": True, "listed": True},
                "visual_slam_odom": {"healthy": False, "listed": True, "readiness_state": "no_messages"},
                "local_odometry": {"healthy": True, "listed": True},
                "raw_lidar": {"healthy": True, "listed": True},
            },
        },
    )
    stack = MappingStackStatus(running=True, pid=1)
    readiness = _readiness_from_status(status, stack_status=stack)
    assert readiness.sensors_ready is False
    assert "visual_slam_odom" in readiness.missing_required


def test_ready_for_preflight_requires_stack_sensors_and_nvblox() -> None:
    readiness = WarehouseMappingReadiness(
        stack_status=MappingStackStatus(running=True, pid=1),
        bridge_reachable=True,
        sensors_ready=True,
        nvblox_ready=True,
    )
    assert readiness.core_ready is True
    assert readiness.mapping_ready is True
    assert readiness.ready_for_preflight is True


def test_core_ready_without_nvblox() -> None:
    readiness = WarehouseMappingReadiness(
        stack_status=MappingStackStatus(running=False, pid=None),
        bridge_reachable=True,
        sensors_ready=True,
        nvblox_ready=False,
    )
    assert readiness.core_ready is True
    assert readiness.mapping_ready is False
    assert readiness.ready_for_preflight is True


def test_ready_for_preflight_without_mapping_stack() -> None:
    readiness = WarehouseMappingReadiness(
        stack_status=MappingStackStatus(running=False, pid=None),
        bridge_reachable=True,
        sensors_ready=True,
        nvblox_ready=False,
    )
    assert readiness.ready_for_preflight is True

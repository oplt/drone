from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service import warehouse_go_preflight as subject
from backend.modules.warehouse.service.flight_health import SubsystemHealth, SubsystemStatus


def _health(status: SubsystemStatus, message: str = "ok") -> SubsystemHealth:
    return SubsystemHealth(status, message)


def _strict(**overrides: Any) -> SimpleNamespace:
    base = {
        "bridge_alive": True,
        "can_perceive_rgb": True,
        "can_perceive_depth": True,
        "can_localize": True,
        "can_scan_lidar": True,
        "missing_required_topics": (),
        "unhealthy_topics": (),
        "suggested_actions": (),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _status(
    *, reachable: bool = True, ready: bool = True, components: dict[str, Any] | None = None
) -> WarehousePerceptionStatus:
    topics = {
        "rgb_image": "/warehouse/front/rgbd/image",
        "depth": "/warehouse/front/rgbd/depth_image",
        "imu": "/imu",
        "visual_slam_odom": "/warehouse/drone/odometry",
        "raw_lidar": "/warehouse/front/rgbd/points",
    }
    diagnostics = {
        key: {
            "expected": topic,
            "matched": topic,
            "healthy": True,
            "listed": True,
            "publishing": True,
            "publisher_count": 1,
            "readiness_state": "ok_graph_presence",
        }
        for key, topic in topics.items()
    }
    return WarehousePerceptionStatus(
        configured=True,
        reachable=reachable,
        ready=ready,
        status="ready" if ready else "degraded",
        profile="gazebo",
        bridge_url="http://127.0.0.1:8088",
        detail="mesh: expected=/nvblox_node/mesh matched=none",
        components={
            "topic_profile": "gazebo",
            "topics": topics,
            "topic_diagnostics": diagnostics,
            "capabilities": {"can_scan_lidar": True},
            "ros_graph": True,
            "ros_bridge_heartbeat": True,
            "health_sample_timestamp": 1_780_000_000.0,
            "missing_required_topics": [],
            "missing_nvblox_topics": ["/nvblox_node/mesh"],
            "nvblox_deferred": True,
            "nvblox_checks_active": False,
            "visual_slam_healthy": True,
            "gazebo": {"sim_publishing": True},
            "tf_tree": True,
            **(components or {}),
        },
    )


@pytest.fixture(autouse=True)
def common_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def ensure_ready() -> SimpleNamespace:
        return SimpleNamespace(
            state="ready",
            bridge_url="http://127.0.0.1:8088",
            last_error=None,
            restart_count=1,
        )

    async def vehicle_runtime() -> tuple[dict[str, Any], None, bool]:
        return {}, None, False

    monkeypatch.setattr(
        "backend.modules.warehouse.service.bridge_stack_lifecycle.ensure_warehouse_bridge_stack_for_preflight",
        ensure_ready,
    )
    monkeypatch.setattr(subject, "_fetch_vehicle_runtime", vehicle_runtime)
    monkeypatch.setattr(
        subject, "readiness_from_perception_status_strict", lambda _status: _strict()
    )
    monkeypatch.setattr(
        subject, "check_bridge", lambda *_args, **_kwargs: _health(SubsystemStatus.OK)
    )
    monkeypatch.setattr(
        subject, "check_sensors", lambda *_args, **_kwargs: _health(SubsystemStatus.OK)
    )
    monkeypatch.setattr(
        subject, "check_slam", lambda *_args, **_kwargs: _health(SubsystemStatus.OK)
    )
    monkeypatch.setattr(
        subject, "check_planner", lambda *_args, **_kwargs: _health(SubsystemStatus.OK)
    )
    monkeypatch.setattr(
        subject, "check_failsafe", lambda *_args, **_kwargs: _health(SubsystemStatus.OK)
    )
    monkeypatch.setattr(
        subject, "check_nvblox", lambda *_args, **_kwargs: _health(SubsystemStatus.WAITING)
    )


async def _run(
    monkeypatch: pytest.MonkeyPatch,
    status: WarehousePerceptionStatus,
    *,
    stable_ms: int = 0,
    takeoff: bool = False,
) -> subject.WarehouseGoPreflight:
    async def fetch_status(**_kwargs: Any) -> WarehousePerceptionStatus:
        return status

    monkeypatch.setattr(subject, "fetch_warehouse_perception_status", fetch_status)
    monkeypatch.setattr(
        subject,
        "evaluate_subsystems_from_components",
        lambda **_kwargs: SimpleNamespace(
            perception_stable_for_ms=stable_ms,
            slam_stable_for_ms=5000,
            ready_to_takeoff=takeoff,
            blocking_reasons=[],
        ),
    )
    return await subject.evaluate_warehouse_go_preflight(deep=True, mission_loaded=True)


@pytest.mark.asyncio
async def test_bridge_ready_with_deferred_nvblox_does_not_report_mesh_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run(monkeypatch, _status(), stable_ms=0, takeoff=False)

    assert result.bridge_ok is True
    assert result.categories["bridge"] == "OK"
    assert result.categories["rgb_depth_imu"] == "OK"
    assert result.categories["lidar"] == "OK"
    assert result.categories["sensors"] == "OK"
    assert result.nvblox_ok is None
    assert result.categories["nvblox"] == "DEFERRED"
    assert "mesh" not in str(result.last_error or "")
    assert result.suggested_actions[0] != "Click Warehouse Preflight to start the ROS bridge stack"
    assert result.diagnostics["topics"]["required_missing"] == []


@pytest.mark.asyncio
async def test_reachable_stale_bridge_health_is_waiting_not_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "check_bridge",
        lambda *_args, **_kwargs: SubsystemHealth(
            SubsystemStatus.WARN,
            "Bridge health sample aging",
            last_seen_ms=6000,
        ),
    )

    result = await _run(monkeypatch, _status(), stable_ms=0, takeoff=False)

    assert result.bridge_ok is True
    assert result.categories["bridge"] == "WAITING"
    assert result.suggested_actions[0] == "Wait for bridge health refresh to complete"
    assert "Click Warehouse Preflight" not in " ".join(result.suggested_actions)


@pytest.mark.asyncio
async def test_unreachable_bridge_fails_and_suggests_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "check_bridge",
        lambda *_args, **_kwargs: _health(SubsystemStatus.FAIL, "Warehouse ROS bridge unreachable"),
    )
    monkeypatch.setattr(
        subject,
        "readiness_from_perception_status_strict",
        lambda _status: _strict(bridge_alive=False),
    )

    result = await _run(
        monkeypatch, _status(reachable=False, ready=False), stable_ms=0, takeoff=False
    )

    assert result.bridge_ok is False
    assert result.categories["bridge"] == "FAIL"
    assert result.suggested_actions[0] == "Click Warehouse Preflight to start the ROS bridge stack"


@pytest.mark.asyncio
async def test_required_sensor_missing_reports_topic_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "check_sensors",
        lambda *_args, **_kwargs: _health(SubsystemStatus.FAIL, "depth missing"),
    )
    monkeypatch.setattr(
        subject,
        "readiness_from_perception_status_strict",
        lambda _status: _strict(
            can_perceive_depth=False,
            missing_required_topics=("depth",),
        ),
    )

    result = await _run(monkeypatch, _status(), stable_ms=0, takeoff=False)

    assert result.categories["sensors"] == "FAIL"
    assert any("Depth topic missing" in reason for reason in result.blocking_reasons)
    assert any(
        "ros2 topic hz /warehouse/front/rgbd/depth_image" in action
        for action in result.suggested_actions
    )


@pytest.mark.asyncio
async def test_latest_ready_health_clears_old_raw_lidar_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run(
        monkeypatch,
        _status(
            components={
                "missing_required_topics": [],
                "raw_lidar_healthy": True,
            }
        ),
        stable_ms=0,
        takeoff=False,
    )

    assert "raw_lidar" not in result.diagnostics["topics"]["required_missing"]
    assert result.categories["lidar"] == "OK"
    assert result.diagnostics["topics"]["by_category"]["lidar_scan"]["status"] == "OK"


@pytest.mark.asyncio
async def test_raw_lidar_truly_missing_is_its_own_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "check_sensors",
        lambda *_args, **_kwargs: _health(SubsystemStatus.FAIL, "raw lidar missing"),
    )
    monkeypatch.setattr(
        subject,
        "readiness_from_perception_status_strict",
        lambda _status: _strict(
            can_scan_lidar=False,
            missing_required_topics=("raw_lidar",),
        ),
    )
    result = await _run(
        monkeypatch,
        _status(
            components={
                "missing_required_topics": ["raw_lidar"],
                "capabilities": {"can_scan_lidar": False},
                "raw_lidar_healthy": False,
            }
        ),
        stable_ms=0,
        takeoff=False,
    )

    assert result.categories["lidar"] == "FAIL"
    assert result.categories["sensors"] == "FAIL"
    assert "raw_lidar" in result.diagnostics["topics"]["required_missing"]
    assert any(
        "ros2 topic hz /warehouse/front/rgbd/points" in action
        for action in result.suggested_actions
    )


@pytest.mark.asyncio
async def test_only_stability_remaining_is_waiting_with_remaining_ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run(monkeypatch, _status(), stable_ms=4000, takeoff=False)

    assert result.categories["bridge"] == "OK"
    assert result.categories["sensors"] == "OK"
    assert result.categories["stability"] == "WAITING"
    assert result.ready_to_fly is False
    assert result.diagnostics["stability"]["remaining_ms"] == 4000


@pytest.mark.asyncio
async def test_stability_elapsed_allows_ready_to_fly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _run(monkeypatch, _status(), stable_ms=8000, takeoff=True)

    assert result.ready_to_fly is True
    assert result.categories["stability"] == "OK"

from __future__ import annotations

import time

import pytest

from backend.modules.warehouse.exceptions import WarehouseMissionFailure
from backend.modules.warehouse.service.runtime_safety import (
    WarehouseRuntimeSafetyTracker,
    odometry_state_is_fresh,
)
from backend.modules.warehouse.service.safety import evaluate_warehouse_runtime_safety
from backend.modules.warehouse.service.takeoff_readiness import readiness_from_perception_status
from backend.modules.warehouse.service.video import (
    effective_drone_video_use_gazebo,
    warehouse_gazebo_sim_enabled,
    warehouse_video_recording_enabled,
    warehouse_video_skip_reason,
)
from backend.modules.warehouse.ports import WarehousePerceptionStatus


def _components_with_odom(*, fresh: bool, tracking_ok: bool = True) -> dict[str, object]:
    mono = time.monotonic() if fresh else time.monotonic() - 30.0
    return {
        "ros_bridge_heartbeat": True,
        "local_odometry_state": {
            "updated_at_monotonic": mono,
            "slam_tracking_ok": tracking_ok,
            "local_north_m": 0.0,
            "local_east_m": 0.0,
        },
        "slam_tracking_ok": False,
        "visual_slam": False,
    }


def test_odometry_state_is_fresh() -> None:
    assert odometry_state_is_fresh(
        {"updated_at_monotonic": time.monotonic()},
        max_age_s=3.0,
    )
    assert not odometry_state_is_fresh(
        {"updated_at_monotonic": time.monotonic() - 10.0},
        max_age_s=3.0,
    )


def test_runtime_safety_ignores_shallow_vslam_when_odometry_fresh() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=0.0)
    decision = tracker.evaluate(_components_with_odom(fresh=True), deep_health=False)
    assert decision.safe is True


def test_runtime_safety_vslam_tracking_lost_after_recovery_grace() -> None:
    tracker = WarehouseRuntimeSafetyTracker(
        startup_grace_s=0.0,
        vslam_recovery_grace_s=0.0,
    )
    components = _components_with_odom(fresh=True, tracking_ok=False)
    decision = tracker.evaluate(components, deep_health=False)
    assert decision.safe is False
    assert decision.reason == "vslam_tracking_lost"


def test_runtime_safety_odometry_stale() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=0.0)
    decision = tracker.evaluate(_components_with_odom(fresh=False), deep_health=False)
    assert decision.safe is False
    assert decision.reason == "odometry_stale"


def test_runtime_safety_uses_live_vslam_topic_when_state_file_stale() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=0.0, odometry_stale_s=2.0)
    components = _components_with_odom(fresh=False)
    components["topic_diagnostics"] = {
        "visual_slam_odom": {
            "healthy": True,
            "publishing": True,
            "publisher_count": 1,
            "readiness_state": "ok",
            "last_message_age_s": 0.05,
            "matched": "/warehouse/drone/odometry",
        }
    }
    decision = tracker.evaluate(components, deep_health=False)
    assert decision.safe is True


def test_runtime_safety_odometry_unreadable_blocks_immediately() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=60.0)
    components = _components_with_odom(fresh=True)
    components["odometry_state_unreadable"] = True
    decision = tracker.evaluate(components, deep_health=False)
    assert decision.safe is False
    assert decision.reason == "odometry_state_unreadable"
    assert decision.action == "hover"


def test_runtime_safety_startup_grace() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=60.0)
    decision = tracker.evaluate({}, deep_health=False)
    assert decision.safe is True
    assert decision.details and decision.details.get("phase") == "startup_grace"


def test_runtime_safety_reset_for_takeoff_restarts_grace() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=30.0)
    tracker.mission_started_at = time.monotonic() - 60.0
    tracker.reset_for_takeoff()
    decision = tracker.evaluate({}, deep_health=False)
    assert decision.safe is True
    assert decision.details and decision.details.get("phase") == "startup_grace"


def test_evaluate_warehouse_runtime_safety_requires_explicit_tracking_false() -> None:
    decision = evaluate_warehouse_runtime_safety(
        {"slam_tracking_ok": False, "visual_slam": True},
    )
    assert decision.reason == "vslam_tracking_lost"


def test_takeoff_readiness_requires_publishing_topics() -> None:
    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components={
            "nvblox_healthy": True,
            "local_odometry_state": {"updated_at_monotonic": time.monotonic()},
            "topic_diagnostics": {
                "rgb_image": {"healthy": True, "listed": True, "publishing": True},
                "depth": {"healthy": True, "listed": True, "publishing": True},
                "imu": {"healthy": False, "listed": True, "readiness_state": "no_messages"},
                "visual_slam_odom": {"healthy": True, "listed": True, "publishing": True},
                "local_odometry": {"healthy": True, "listed": True, "publishing": True},
                "raw_lidar": {"healthy": True, "listed": True, "publishing": True},
            },
        },
    )
    readiness = readiness_from_perception_status(status, require_nvblox=False)
    assert readiness.ready is False
    assert "imu" in readiness.stale_topics


def test_takeoff_ready_without_nvblox() -> None:
    status = WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=True,
        status="ready",
        components={
            "nvblox_healthy": False,
            "nvblox_warming_up": True,
            "local_odometry_state": {"updated_at_monotonic": time.monotonic()},
            "topic_diagnostics": {
                key: {"healthy": True, "listed": True, "publishing": True}
                for key in (
                    "rgb_image",
                    "depth",
                    "imu",
                    "visual_slam_odom",
                    "local_odometry",
                    "raw_lidar",
                )
            },
        },
    )
    readiness = readiness_from_perception_status(status, require_nvblox=False)
    assert readiness.ready is True


def test_warehouse_mission_failure_payload() -> None:
    failure = WarehouseMissionFailure(
        reason="vslam_tracking_lost",
        action="return_or_land",
        details={"loss_duration_s": 4.2},
    )
    assert failure.to_event_payload()["reason"] == "vslam_tracking_lost"


def test_runtime_safety_topic_missing_ignored_when_odometry_fresh() -> None:
    tracker = WarehouseRuntimeSafetyTracker(startup_grace_s=0.0, odometry_stale_s=12.0)
    components = _components_with_odom(fresh=True)
    components["topic_diagnostics"] = {
        "visual_slam_odom": {
            "healthy": False,
            "readiness_state": "topic_missing",
            "expected": "/warehouse/drone/odometry",
        }
    }
    decision = tracker.evaluate(components, deep_health=True)
    assert decision.safe is True


def test_gazebo_video_skip_without_use_gazebo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")
    from backend.core.config.runtime import settings

    monkeypatch.setattr(settings, "drone_video_use_gazebo", False, raising=False)
    monkeypatch.setattr(settings, "drone_video_enabled", True, raising=False)
    monkeypatch.setattr(settings, "drone_video_source_gazebo", "", raising=False)
    assert warehouse_gazebo_sim_enabled()
    assert warehouse_video_skip_reason() is not None
    assert warehouse_video_recording_enabled() is False


def test_gazebo_video_auto_enabled_with_gazebo_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")
    from backend.core.config.runtime import settings
    from backend.modules.warehouse.service.video import effective_drone_video_use_gazebo

    monkeypatch.setattr(settings, "drone_video_use_gazebo", False, raising=False)
    monkeypatch.setattr(settings, "drone_video_source_gazebo", "udp://127.0.0.1:5600", raising=False)
    assert effective_drone_video_use_gazebo() is True

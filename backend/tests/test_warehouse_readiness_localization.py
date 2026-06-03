from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from backend.modules.warehouse.ports import WarehousePerceptionStatus
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import (
    SubsystemStatus,
    check_nvblox,
    check_slam,
)
from backend.modules.warehouse.service.flight_readiness import (
    compute_warehouse_flight_readiness,
    evaluate_subsystems_from_components,
)
from backend.modules.warehouse.service.localization_mode import LocalizationMode
from backend.modules.warehouse.service.perception_stability import (
    PerceptionStabilityTracker,
    get_perception_stability_tracker,
    perception_core_ok,
)
from backend.modules.warehouse.service.readiness_result import (
    evaluate_warehouse_capabilities,
    readiness_from_perception_status_strict,
)
from backend.modules.warehouse.service.flight_health import (
    SubsystemHealth,
    check_bridge,
    check_sensors,
)


def _live_diag() -> dict[str, object]:
    return {
        "healthy": True,
        "readiness_state": "ok_via_messages",
        "publisher_count": 1,
        "publishing": True,
        "last_message_age_s": 0.05,
        "hz": 20.0,
    }


def _status(components: dict[str, object]) -> WarehousePerceptionStatus:
    return WarehousePerceptionStatus(
        configured=True,
        reachable=True,
        ready=False,
        status="degraded",
        profile="gazebo",
        bridge_url="http://127.0.0.1:8088",
        components=components,
    )


def _gazebo_components(
    *,
    slam_tracking_ok: bool | None = True,
    include_depth: bool = True,
    nvblox_deferred: bool = True,
    mapping_stack_running: bool = False,
) -> dict[str, object]:
    diagnostics = {
        "visual_slam_odom": _live_diag(),
        "rgb_image": _live_diag(),
        "imu": _live_diag(),
        "raw_lidar": _live_diag(),
    }
    if include_depth:
        diagnostics["depth"] = _live_diag()
    odom_state = {
        "updated_at_monotonic": __import__("time").monotonic(),
        "slam_tracking_ok": slam_tracking_ok,
        "slam_tracking_status": "GAZEBO_GROUND_TRUTH_OK",
        "frame_id": "odom",
        "child_frame_id": "base_link",
        "local_position_ok": True,
    }
    return {
        "ros_graph": True,
        "ros_topic_count": 12,
        "topics": {
            "visual_slam_odom": "/warehouse/contract/odometry",
            "depth": "/warehouse/contract/depth/image",
            "rgb_image": "/warehouse/contract/rgb/image",
            "imu": "/warehouse/contract/imu",
        },
        "topic_diagnostics": diagnostics,
        "local_odometry_state": odom_state,
        "slam_tracking_ok": slam_tracking_ok,
        "localization_mode": LocalizationMode.GAZEBO_GROUND_TRUTH.value,
        "tf_chain": {"chain_ok": True},
        "tf_tree": True,
        "nvblox_deferred": nvblox_deferred,
        "nvblox_checks_active": mapping_stack_running,
        "missing_nvblox_topics": ["/nvblox_node/mesh"] if nvblox_deferred else [],
        "gazebo": {"sim_publishing": True},
        "health_sample_timestamp": __import__("time").time(),
        "cache_ready": True,
    }


@pytest.fixture
def gazebo_localization_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_LOCALIZATION_MODE", "gazebo_ground_truth")
    monkeypatch.setenv("WAREHOUSE_BRIDGE_FLOW", "gazebo")
    monkeypatch.setenv("WAREHOUSE_GAZEBO_SIM", "1")


@pytest.fixture
def visual_slam_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAREHOUSE_LOCALIZATION_MODE", "visual_slam")
    monkeypatch.setenv("WAREHOUSE_BRIDGE_FLOW", "isaac")


def test_gazebo_mode_passes_without_real_slam_tracking(
    gazebo_localization_mode: None,
) -> None:
    components = _gazebo_components(slam_tracking_ok=False)
    config = WarehouseFlightConfig.from_env()
    slam = check_slam(components, config)
    assert slam.status != SubsystemStatus.FAIL


def test_visual_slam_mode_fails_when_tracking_lost(
    visual_slam_mode: None,
) -> None:
    components = _gazebo_components(slam_tracking_ok=False)
    components["localization_mode"] = LocalizationMode.VISUAL_SLAM.value
    config = WarehouseFlightConfig.from_env()
    slam = check_slam(components, config)
    assert slam.status == SubsystemStatus.FAIL
    assert "tracking" in slam.message.lower() or "odometry" in slam.message.lower()


def test_missing_depth_fails_sensors(gazebo_localization_mode: None) -> None:
    components = _gazebo_components(include_depth=False)
    diagnostics = dict(components["topic_diagnostics"])  # type: ignore[arg-type]
    diagnostics.pop("depth", None)
    components["topic_diagnostics"] = diagnostics
    config = WarehouseFlightConfig.from_env()
    sensors = check_sensors(components, config)
    assert sensors.status == SubsystemStatus.FAIL


def test_nvblox_deferred_during_preflight(gazebo_localization_mode: None) -> None:
    components = _gazebo_components(nvblox_deferred=True, mapping_stack_running=False)
    config = WarehouseFlightConfig.from_env()
    nvblox = check_nvblox(components, config, mapping_stack_running=False)
    assert nvblox.status == SubsystemStatus.WAITING
    assert nvblox.details.get("deferred") is True


def test_nvblox_ok_when_costmap_age_not_sampled(gazebo_localization_mode: None) -> None:
    components = _gazebo_components(nvblox_deferred=False, mapping_stack_running=True)
    components["nvblox_checks_active"] = True
    components["nvblox_healthy"] = True
    components["nvblox"] = True
    components["topic_diagnostics"]["esdf"] = {
        "key": "esdf",
        "healthy": True,
        "readiness_state": "shallow_present",
        "listed": True,
        "matched": "/nvblox_node/static_esdf_pointcloud",
        "publisher_count": 1,
        "publishing": True,
    }
    config = WarehouseFlightConfig.from_env()
    nvblox = check_nvblox(components, config, mapping_stack_running=True)
    assert nvblox.status == SubsystemStatus.OK
    assert "not sampled" in nvblox.message


def test_nvblox_fails_during_active_mapping(visual_slam_mode: None) -> None:
    components = _gazebo_components(nvblox_deferred=False, mapping_stack_running=True)
    components["nvblox_checks_active"] = True
    components["nvblox_healthy"] = False
    components["missing_nvblox_topics"] = ["/nvblox_node/mesh"]
    config = WarehouseFlightConfig.from_env()
    nvblox = check_nvblox(components, config, mapping_stack_running=True)
    assert nvblox.status == SubsystemStatus.FAIL


def test_stability_timer_advances_when_core_ok(gazebo_localization_mode: None) -> None:
    tracker = PerceptionStabilityTracker()
    components = _gazebo_components()
    config = WarehouseFlightConfig.from_env()
    status = _status(components)
    bridge = check_bridge(status, components)
    sensors = check_sensors(components, config)
    slam = check_slam(components, config)
    nvblox = check_nvblox(components, config)
    assert perception_core_ok(
        bridge=bridge,
        sensors=sensors,
        slam=slam,
        nvblox=nvblox,
        components=components,
        require_nvblox=config.require_nvblox_for_autonomy,
    )
    tracker.stable_for_ms(perception_ok=True)
    assert tracker.stable_for_ms(perception_ok=True) >= 0


def test_stability_timer_resets_with_reason() -> None:
    tracker = PerceptionStabilityTracker()
    tracker.stable_for_ms(perception_ok=True)
    tracker.stable_for_ms(perception_ok=False, reset_reason="tracking lost")
    assert tracker.stable_for_ms(perception_ok=False) == 0
    assert tracker.last_reset_reason == "tracking lost"


def test_health_reachable_does_not_imply_ready_to_fly(gazebo_localization_mode: None) -> None:
    result = readiness_from_perception_status_strict(
        _status(
            {
                "ros_graph": True,
                "ros_topic_count": 1,
                "topics": {"rgb_image": "/warehouse/contract/rgb/image"},
                "topic_diagnostics": {"rgb_image": _live_diag()},
            }
        )
    )
    assert result.bridge_alive is True
    assert result.can_fly_warehouse_scan is False


def test_missing_nvblox_not_failed_in_strict_readiness(gazebo_localization_mode: None) -> None:
    components = _gazebo_components()
    result = readiness_from_perception_status_strict(
        _status(components),
        require_nvblox_for_map=False,
    )
    assert "/nvblox_node/mesh" in result.missing_nvblox_topics or result.missing_nvblox_topics
    assert result.can_fly_warehouse_scan is True


def test_flight_readiness_blocks_takeoff_when_slam_fails(visual_slam_mode: None) -> None:
    components = _gazebo_components(slam_tracking_ok=False)
    components["localization_mode"] = LocalizationMode.VISUAL_SLAM.value
    readiness = evaluate_subsystems_from_components(
        status=_status(components),
        components=components,
        telemetry=None,
        config=WarehouseFlightConfig.from_env(),
    )
    assert readiness.ready_to_takeoff is False


def _shallow_listed_diag() -> dict[str, object]:
    return {
        "healthy": True,
        "readiness_state": "shallow_present",
        "listed": True,
        "publisher_count": 1,
        "publishing": True,
    }


def test_gazebo_sim_publishing_passes_with_shallow_ros_probes(
    gazebo_localization_mode: None,
) -> None:
    components = {
        "ros_graph": False,
        "ros_topic_count": 0,
        "topic_profile": "gazebo",
        "topics": {
            "visual_slam_odom": "/warehouse/contract/odometry",
            "depth": "/warehouse/contract/depth/image",
            "rgb_image": "/warehouse/contract/rgb/image",
            "imu": "/warehouse/contract/imu",
        },
        "topic_diagnostics": {
            "visual_slam_odom": _shallow_listed_diag(),
            "rgb_image": _shallow_listed_diag(),
            "depth": _shallow_listed_diag(),
            "imu": _shallow_listed_diag(),
        },
        "gazebo": {
            "sim_publishing": True,
            "rgb_publishing": True,
            "depth_publishing": True,
            "odom_publishing": True,
            "imu_publishing": True,
        },
        "health_sample_timestamp": __import__("time").time(),
    }
    caps = evaluate_warehouse_capabilities(_status(components))
    assert caps["can_perceive_rgb"] is True
    assert caps["can_perceive_depth"] is True
    assert caps["can_localize"] is True
    assert caps["ros_graph_ready"] is True

    config = WarehouseFlightConfig.from_env()
    sensors = check_sensors(components, config)
    assert sensors.status != SubsystemStatus.FAIL

    strict = readiness_from_perception_status_strict(_status(components))
    assert strict.can_fly_warehouse_scan is True


def test_bridge_ok_without_ready_to_fly_gate() -> None:
    readiness = compute_warehouse_flight_readiness(
        bridge=SubsystemHealth(SubsystemStatus.OK, "ok"),
        autopilot=SubsystemHealth(SubsystemStatus.OK, "ok"),
        sensors=SubsystemHealth(SubsystemStatus.FAIL, "depth missing"),
        slam=SubsystemHealth(SubsystemStatus.FAIL, "tracking"),
        nvblox=SubsystemHealth(SubsystemStatus.WAITING, "deferred"),
        planner=SubsystemHealth(SubsystemStatus.WAITING, "mission"),
        failsafe=SubsystemHealth(SubsystemStatus.OK, "ok"),
        config=WarehouseFlightConfig.from_env(),
        stable_for_ms=0,
        perception_stable_for_ms=0,
    )
    assert readiness.subsystems["bridge"].status == SubsystemStatus.OK
    assert readiness.ready_to_takeoff is False

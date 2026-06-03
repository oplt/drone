from __future__ import annotations

import time

from backend.modules.warehouse.service.flight_readiness import evaluate_subsystems_from_components
from backend.modules.warehouse.service.perception_stability import get_perception_stability_tracker
from backend.modules.warehouse.service.readiness_cache import (
    clear_sensor_readiness,
    record_sensor_readiness,
    sensor_readiness_recent,
)
from backend.modules.warehouse.service.scan_preflight import _result_from_recent_go_preflight
from backend.modules.warehouse.service.warehouse_go_preflight import (
    _aggregate_status,
    _topic_status,
)


def test_topic_status_honors_strict_missing() -> None:
    components = {"topic_diagnostics": {"rgb_image": {"healthy": True, "readiness_state": "ok"}}}
    assert (
        _topic_status(
            "rgb_image",
            components,
            strict_missing=("rgb_image",),
            strict_unhealthy=(),
        )
        == "FAIL"
    )


def test_aggregate_status_fails_when_any_topic_fails() -> None:
    assert _aggregate_status(["OK", "FAIL", "WAITING"]) == "FAIL"


def test_stability_holds_during_probe_when_window_started() -> None:
    tracker = get_perception_stability_tracker()
    tracker.reset(reason="test reset")
    tracker.stable_for_ms(perception_ok=True)
    time.sleep(0.05)
    held = tracker.hold_stable_ms()
    assert held > 0
    during_probe = tracker.stable_for_ms(
        perception_ok=False,
        reset_reason="ROS health probe in progress",
    )
    assert during_probe == 0
    assert tracker.hold_stable_ms() == 0


def test_sensor_readiness_cache_clears() -> None:
    clear_sensor_readiness()
    record_sensor_readiness(
        ready=True,
        payload={"can_fly_warehouse_scan": True},
    )
    assert sensor_readiness_recent(max_age_s=60.0)
    clear_sensor_readiness()
    assert not sensor_readiness_recent(max_age_s=60.0)


def test_reused_go_preflight_payload_requires_can_fly() -> None:
    clear_sensor_readiness()
    record_sensor_readiness(ready=True, payload={"can_fly_warehouse_scan": False})
    assert _result_from_recent_go_preflight() is None


def test_evaluate_subsystems_probe_holds_perception_stable_ms() -> None:
    tracker = get_perception_stability_tracker()
    tracker.reset(reason="test reset")

    class _Status:
        reachable = True
        ready = True
        profile = "gazebo"

    components = {
        "diagnostics_ready": True,
        "cache_ready": False,
        "probe_in_progress": True,
        "slam_tracking_ok": True,
        "topic_diagnostics": {
            "rgb_image": {"healthy": True, "readiness_state": "ok"},
            "depth": {"healthy": True, "readiness_state": "ok"},
            "imu": {"healthy": True, "readiness_state": "ok"},
            "visual_slam_odom": {"healthy": True, "readiness_state": "ok"},
        },
        "gazebo": {"sim_publishing": True},
        "tf_chain": {"chain_ok": True},
    }
    from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig

    config = WarehouseFlightConfig.from_env()
    tracker.stable_for_ms(perception_ok=True)
    time.sleep(0.05)
    readiness = evaluate_subsystems_from_components(
        status=_Status(),
        components=components,
        telemetry=None,
        config=config,
    )
    assert readiness.perception_stable_for_ms > 0

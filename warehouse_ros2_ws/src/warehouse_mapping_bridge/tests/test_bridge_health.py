from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from warehouse_mapping_bridge.config import BridgeConfig
from warehouse_mapping_bridge.session import BridgeState


@pytest.fixture
def bridge_state(tmp_path, monkeypatch) -> BridgeState:
    monkeypatch.setenv("WAREHOUSE_HEALTH_BACKGROUND_PROBE", "0")
    config = BridgeConfig(
        host="127.0.0.1",
        port=8088,
        profile="gazebo",
        capture_root=tmp_path,
        ros_ws_url="ws://127.0.0.1:9090",
        autolaunch=False,
        launch_cmd="true",
        mavlink_vision_url="",
        odometry_state_path=tmp_path / "odometry.json",
    )
    return BridgeState(config)


def test_shallow_health_is_cache_only_and_fast(bridge_state: BridgeState) -> None:
    with patch.object(BridgeState, "_build_health") as build_health:
        build_health.side_effect = AssertionError("shallow /health must not probe ROS")

        empty = bridge_state.health(deep=False)
        assert empty["probe_mode"] == "cache_empty"
        assert empty["from_cache"] is False
        assert build_health.call_count == 0

        now = time.monotonic()
        cached_payload = {
            "status": "ready",
            "ready": True,
            "components": {"ros_bridge_heartbeat": True},
        }
        with bridge_state._health_lock:
            bridge_state._shallow_health_cache = (now, dict(cached_payload))

        shallow = bridge_state.health(deep=False)
        assert shallow["from_cache"] is True
        assert shallow["probe_mode"] == "shallow_cached"
        assert shallow["ready"] is True
        assert build_health.call_count == 0


def test_deep_health_returns_cached_probe_when_lock_held(bridge_state: BridgeState) -> None:
    cached_payload = {
        "status": "degraded",
        "ready": False,
        "components": {"ros_topic_count": 12},
    }
    now = time.monotonic()
    with bridge_state._health_lock:
        bridge_state._deep_health_cache = (now, dict(cached_payload))
        bridge_state._deep_probe_in_progress = True

    result = bridge_state.health(deep=True)
    assert result["from_cache"] is True
    assert result["probe_in_progress"] is True
    assert result["components"]["ros_topic_count"] == 12


def test_deep_health_returns_shallow_cache_when_probe_in_progress(
    bridge_state: BridgeState,
) -> None:
    now = time.monotonic()
    with bridge_state._health_lock:
        bridge_state._shallow_health_cache = (
            now,
            {"status": "degraded", "ready": False, "components": {"ros_topic_count": 4}},
        )
        bridge_state._deep_probe_in_progress = True

    result = bridge_state.health(deep=True)
    assert result["from_cache"] is True
    assert result["probe_mode"] == "shallow_cached"
    assert result["probe_in_progress"] is True
    assert result["components"]["ros_topic_count"] == 4


def test_deep_health_single_flight_blocks_overlapping_probe(bridge_state: BridgeState) -> None:
    cached_payload = {"status": "ready", "ready": True, "components": {}}
    now = time.monotonic()
    with bridge_state._health_lock:
        bridge_state._deep_health_cache = (now, dict(cached_payload))

    bridge_state._deep_probe_lock.acquire()
    bridge_state._deep_probe_in_progress = True
    try:
        result = bridge_state.health(deep=True)
        assert result["from_cache"] is True
        assert result["probe_in_progress"] is True
    finally:
        bridge_state._deep_probe_in_progress = False
        bridge_state._deep_probe_lock.release()


def test_shallow_topic_diagnostic_marks_listed_topics_present(bridge_state: BridgeState) -> None:
    diag = bridge_state._shallow_topic_diagnostic(
        "rgb_image",
        "/warehouse/front/rgbd/image",
        {"/warehouse/front/rgbd/image"},
    )
    assert diag.healthy is True
    assert diag.readiness_state == "shallow_present"
    assert diag.error is None

    missing = bridge_state._shallow_topic_diagnostic(
        "depth",
        "/warehouse/front/rgbd/depth_image",
        set(),
    )
    assert missing.healthy is False
    assert missing.readiness_state == "topic_missing"


def test_deep_probe_updates_shallow_cache(bridge_state: BridgeState) -> None:
    deep_payload = {
        "status": "ready",
        "ready": True,
        "detail": None,
        "components": {"ros_bridge_heartbeat": True},
    }

    with patch.object(BridgeState, "_build_health", return_value=deep_payload):
        result = bridge_state.health(deep=True)

    assert result["probe_mode"] == "deep"
    assert result["from_cache"] is False
    shallow = bridge_state.health(deep=False)
    assert shallow["from_cache"] is True
    assert shallow["probe_mode"] == "shallow_cached"


def test_deep_health_uses_cache_when_background_probe_enabled(
    bridge_state: BridgeState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge_state, "_background_probe_enabled", lambda: True)
    with patch.object(BridgeState, "_build_health") as build_health:
        build_health.side_effect = AssertionError("background deep health must not block")
        result = bridge_state.health(deep=True)

    assert result["probe_mode"] == "cache_empty"
    assert result["probe_in_progress"] in {True, False}
    assert build_health.call_count == 0


def test_stale_shallow_health_does_not_refresh_during_deep_probe(
    bridge_state: BridgeState,
) -> None:
    with bridge_state._health_lock:
        bridge_state._shallow_health_cache = (
            time.monotonic() - 30,
            {"status": "degraded", "ready": False, "components": {"ros_topic_count": 4}},
        )
        bridge_state._deep_probe_in_progress = True

    with patch.object(bridge_state, "_refresh_shallow_payload") as refresh:
        refresh.side_effect = AssertionError("active deep probe should keep /health cached")
        result = bridge_state.health(deep=False)

    assert result["from_cache"] is True
    assert result["probe_in_progress"] is True
    assert result["components"]["ros_topic_count"] == 4
    assert refresh.call_count == 0


def test_stale_shallow_refresh_runs_outside_health_lock(
    bridge_state: BridgeState,
) -> None:
    with bridge_state._health_lock:
        bridge_state._shallow_health_cache = (
            time.monotonic() - 30,
            {"status": "degraded", "ready": False, "components": {"ros_topic_count": 4}},
        )

    def refresh(payload: dict[str, object]) -> dict[str, object]:
        assert bridge_state._health_lock.acquire(blocking=False)
        bridge_state._health_lock.release()
        return {
            **payload,
            "status": "ready",
            "ready": True,
            "components": {"ros_topic_count": 10},
        }

    with patch.object(bridge_state, "_refresh_shallow_payload", side_effect=refresh):
        result = bridge_state.health(deep=False)

    assert result["status"] == "ready"
    assert result["ready"] is True
    assert result["components"]["ros_topic_count"] == 10


def test_nvblox_health_checks_deferred_when_node_absent(
    bridge_state: BridgeState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAREHOUSE_BRIDGE_HEALTH_CHECK_NVBLOX", "auto")
    assert BridgeState._nvblox_health_checks_enabled(set()) is False
    assert BridgeState._nvblox_health_checks_enabled({"/nvblox_node/mesh"}) is True
    assert BridgeState._nvblox_health_checks_enabled(set()) is False
    monkeypatch.setenv("WAREHOUSE_BRIDGE_HEALTH_CHECK_NVBLOX", "never")
    assert BridgeState._nvblox_health_checks_enabled({"/nvblox_node/mesh"}) is False

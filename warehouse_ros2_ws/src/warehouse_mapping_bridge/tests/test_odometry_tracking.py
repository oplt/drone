from __future__ import annotations

import time

from warehouse_mapping_bridge.session import BridgeState


def test_fresh_live_vslam_topic_overrides_legacy_false_tracking_flag() -> None:
    fresh, age_s, tracking_ok = BridgeState._odometry_tracking_state(
        {
            "updated_at_monotonic": time.monotonic(),
            "odom_received": True,
            "slam_tracking_ok": False,
        },
        deep_probe=True,
        vslam_topic_ready=True,
    )

    assert fresh is True
    assert age_s is not None
    assert tracking_ok is True


def test_fresh_odom_keeps_false_tracking_when_vslam_topic_unhealthy() -> None:
    fresh, _age_s, tracking_ok = BridgeState._odometry_tracking_state(
        {
            "updated_at_monotonic": time.monotonic(),
            "odom_received": True,
            "slam_tracking_ok": False,
        },
        deep_probe=True,
        vslam_topic_ready=False,
    )

    assert fresh is True
    assert tracking_ok is False

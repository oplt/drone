from __future__ import annotations

import types

from warehouse_mapping_bridge.config import topic_registry
from warehouse_mapping_bridge.odometry_export_node import normalize_odometry_frames
from warehouse_mapping_bridge.session import BridgeState
from warehouse_mapping_bridge.topic_diagnostics import probe_tf_chain


def _fake_odom(frame_id: str = "bad_odom", child_frame_id: str = "bad_base") -> object:
    return types.SimpleNamespace(
        header=types.SimpleNamespace(frame_id=frame_id),
        child_frame_id=child_frame_id,
    )


def test_odometry_frames_normalize_to_gazebo_canonical(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "gazebo")
    topic_registry.cache_clear()
    frames = topic_registry().frames

    odom = normalize_odometry_frames(
        _fake_odom(),
        odom_frame=frames["odom"],
        base_link_frame=frames["base_link"],
    )

    assert odom.header.frame_id == "odom"
    assert odom.child_frame_id == "iris_with_standoffs/base_link"
    topic_registry.cache_clear()


def test_missing_odom_to_base_transform_fails_tf_validation(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "gazebo")
    topic_registry.cache_clear()
    monkeypatch.setattr(
        "warehouse_mapping_bridge.topic_diagnostics._tf_echo_ok",
        lambda parent, child: False,
    )
    monkeypatch.setattr(
        "warehouse_mapping_bridge.topic_diagnostics._gazebo_odom_declares_tf_edge",
        lambda *_args, **_kwargs: (False, None),
    )
    monkeypatch.setattr(
        "warehouse_mapping_bridge.topic_diagnostics._static_tf_edge_ok",
        lambda *_args, **_kwargs: False,
    )

    diag = probe_tf_chain()

    assert diag.chain_ok is False
    assert ("odom", "iris_with_standoffs/base_link") in diag.missing_tf_edges
    topic_registry.cache_clear()


def test_present_tf_edges_pass_validation(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "gazebo")
    topic_registry.cache_clear()
    monkeypatch.setattr(
        "warehouse_mapping_bridge.topic_diagnostics._tf_echo_ok",
        lambda parent, child: True,
    )
    monkeypatch.setattr(
        "warehouse_mapping_bridge.topic_diagnostics._sim_clock_publishing",
        lambda: True,
    )

    diag = probe_tf_chain()

    assert diag.chain_ok is True
    assert diag.missing_tf_edges == ()
    topic_registry.cache_clear()


def test_mapping_not_ready_when_tf_missing() -> None:
    capabilities = BridgeState._build_capabilities(
        bridge_alive=True,
        ros_graph_ready=True,
        topic_health={
            "visual_slam_odom": True,
            "depth": True,
            "rgb_image": True,
            "raw_lidar": True,
            "imu": True,
        },
        nvblox_ready=True,
        odom_fresh=True,
        require_lidar=True,
        tf_tree=False,
    )

    assert capabilities["can_fly_warehouse_scan"] is True
    assert capabilities["can_map_3d"] is False
    assert capabilities["can_avoid_obstacles"] is False

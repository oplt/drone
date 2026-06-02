from __future__ import annotations

from warehouse_mapping_bridge.ros_graph import rclpy_topic_names


def test_rclpy_topic_names_returns_set_or_none() -> None:
    topics = rclpy_topic_names(timeout_s=0.01)

    assert topics is None or isinstance(topics, set)

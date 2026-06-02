from __future__ import annotations

from warehouse_mapping_bridge.config import topic_registry


def test_isaac_topic_profile_uses_single_expected_defaults(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "isaac_ros_nvblox_stereo")
    topic_registry.cache_clear()
    registry = topic_registry()

    assert registry.topics["left_image"] == "/left/image_rect"
    assert registry.topics["right_image"] == "/right/image_rect"
    assert registry.topics["depth"] == "/depth"
    assert registry.topics["raw_lidar"] == "/lidar/points"
    assert registry.topics["pointcloud"] == "/nvblox_node/static_esdf_pointcloud"

    topic_registry.cache_clear()


def test_unknown_topic_profile_fails_fast(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "does_not_exist")
    topic_registry.cache_clear()
    try:
        try:
            topic_registry()
        except ValueError as exc:
            assert "Unknown warehouse topic profile" in str(exc)
        else:
            raise AssertionError("unknown profile should fail")
    finally:
        topic_registry.cache_clear()

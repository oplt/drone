from __future__ import annotations

import yaml
from pathlib import Path

from warehouse_mapping_bridge.config import source_topic_env, topic_registry


def test_isaac_topic_profile_uses_single_expected_defaults(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "isaac_ros_nvblox_stereo")
    topic_registry.cache_clear()
    registry = topic_registry()

    assert registry.topics["left_image"] == "/warehouse/contract/stereo/left/image"
    assert registry.topics["right_image"] == "/warehouse/contract/stereo/right/image"
    assert registry.topics["depth"] == "/warehouse/contract/depth/image"
    assert registry.topics["raw_lidar"] == "/warehouse/contract/points"
    assert registry.topics["pointcloud"] == "/warehouse/contract/map/points"
    assert source_topic_env("isaac_ros_nvblox_stereo")["depth"] == "/depth"

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


def test_gazebo_topic_profile_has_sensor_topics(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "gazebo")
    topic_registry.cache_clear()
    registry = topic_registry()

    assert registry.topics["rgb_image"] == "/warehouse/contract/rgb/image"
    assert registry.topics["depth"] == "/warehouse/contract/depth/image"
    assert registry.topics["imu"] == "/warehouse/contract/imu"
    assert registry.topics["visual_slam_odom"] == "/warehouse/contract/odometry"
    assert registry.topics["local_odometry"] == "/warehouse/contract/local_odometry"
    assert registry.topics["local_odometry"] != registry.topics["visual_slam_odom"]
    assert registry.topics["raw_lidar"] == "/warehouse/contract/points"
    assert source_topic_env("gazebo")["depth"] == "/warehouse/front/rgbd/depth_image"
    assert source_topic_env("gazebo")["raw_lidar"] == "/warehouse/mid360/scan/points"

    topic_registry.cache_clear()


def test_real_device_topic_profile_has_hardware_topics(monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_TOPIC_PROFILE", "real_device")
    topic_registry.cache_clear()
    registry = topic_registry()

    assert registry.topics["rgb_image"] == "/warehouse/contract/rgb/image"
    assert registry.topics["depth"] == "/warehouse/contract/depth/image"
    assert registry.topics["imu"] == "/warehouse/contract/imu"
    assert registry.topics["raw_lidar"] == "/warehouse/contract/points"
    assert registry.topics["visual_slam_odom"] == "/warehouse/contract/odometry"
    assert source_topic_env("real_device")["imu"] == "/imu/data"

    topic_registry.cache_clear()


def test_gazebo_defaults_do_not_use_isaac_topics() -> None:
    defaults = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config" / "defaults_gazebo.yaml").read_text(
            encoding="utf-8"
        )
    )
    params = defaults["/**"]["ros__parameters"]

    assert params["profile"] == "gazebo"
    assert params["visual_slam_odom_topic"] == "/warehouse/contract/odometry"
    assert params["imu_topic"] == "/warehouse/contract/imu"
    assert params["raw_lidar_topic"] == "/warehouse/contract/points"

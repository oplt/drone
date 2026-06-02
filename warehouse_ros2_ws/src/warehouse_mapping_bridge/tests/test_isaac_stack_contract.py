from __future__ import annotations

from warehouse_mapping_bridge.isaac_stack_contract import (
    expected_topics,
    load_stack_commands,
    missing_required_commands,
)


def test_isaac_stack_contract_lists_required_commands(monkeypatch) -> None:
    for name in (
        "WAREHOUSE_CAMERA_LAUNCH_CMD",
        "WAREHOUSE_IMU_LAUNCH_CMD",
        "WAREHOUSE_IMAGE_PIPELINE_LAUNCH_CMD",
        "WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD",
        "WAREHOUSE_DEPTH_LAUNCH_CMD",
        "WAREHOUSE_NVBLOX_LAUNCH_CMD",
    ):
        monkeypatch.delenv(name, raising=False)

    commands = load_stack_commands()
    missing = missing_required_commands(commands)

    assert {command.env for command in missing} == {
        "WAREHOUSE_CAMERA_LAUNCH_CMD",
        "WAREHOUSE_IMU_LAUNCH_CMD",
        "WAREHOUSE_IMAGE_PIPELINE_LAUNCH_CMD",
        "WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD",
        "WAREHOUSE_DEPTH_LAUNCH_CMD",
        "WAREHOUSE_NVBLOX_LAUNCH_CMD",
    }
    assert "/visual_slam/tracking/odometry" in expected_topics(commands)
    assert "/nvblox_node/static_esdf_pointcloud" in expected_topics(commands)


def test_isaac_stack_contract_accepts_configured_commands(monkeypatch) -> None:
    for name in (
        "WAREHOUSE_CAMERA_LAUNCH_CMD",
        "WAREHOUSE_IMU_LAUNCH_CMD",
        "WAREHOUSE_IMAGE_PIPELINE_LAUNCH_CMD",
        "WAREHOUSE_VISUAL_SLAM_LAUNCH_CMD",
        "WAREHOUSE_DEPTH_LAUNCH_CMD",
        "WAREHOUSE_NVBLOX_LAUNCH_CMD",
    ):
        monkeypatch.setenv(name, "ros2 launch example_pkg example.launch.py")

    assert missing_required_commands(load_stack_commands()) == []

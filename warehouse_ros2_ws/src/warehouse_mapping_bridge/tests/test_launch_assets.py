from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_simulation_assets_exist() -> None:
    assert (PACKAGE_ROOT / "worlds" / "warehouse_empty.sdf").is_file()
    assert (PACKAGE_ROOT / "urdf" / "warehouse_drone.urdf").is_file()
    assert (PACKAGE_ROOT / "models" / "warehouse_drone" / "model.sdf").is_file()
    assert (PACKAGE_ROOT / "config" / "gazebo_bridge.yaml").is_file()
    assert (PACKAGE_ROOT / "config" / "defaults_real_device.yaml").is_file()
    assert (PACKAGE_ROOT / "launch" / "real_device_warehouse_mapping.launch.py").is_file()


def test_gazebo_bridge_config_contains_required_sensor_flow() -> None:
    mappings = yaml.safe_load((PACKAGE_ROOT / "config" / "gazebo_bridge.yaml").read_text())
    ros_topics = {mapping["ros_topic_name"] for mapping in mappings}

    assert "/clock" in ros_topics
    assert "/warehouse/front/rgbd/image" in ros_topics
    assert "/warehouse/front/rgbd/depth_image" in ros_topics
    assert "/warehouse/front/rgbd/camera_info" in ros_topics
    assert "/warehouse/front/rgbd/points" in ros_topics
    assert "/warehouse/drone/odometry" in ros_topics
    assert "/warehouse/drone/imu" in ros_topics


def test_launch_files_compile() -> None:
    for path in (PACKAGE_ROOT / "launch").glob("*.launch.py"):
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")


def test_launch_files_import_when_ros_launch_deps_available() -> None:
    pytest.importorskip("lark")
    pytest.importorskip("launch")
    pytest.importorskip("launch_ros")

    for path in (PACKAGE_ROOT / "launch").glob("*.launch.py"):
        spec = importlib.util.spec_from_file_location(path.stem.replace(".", "_"), path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        description = module.generate_launch_description()
        assert description.entities

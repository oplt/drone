from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_simulation_assets_exist() -> None:
    assert (PACKAGE_ROOT / "worlds" / "warehouse_empty.sdf").is_file()
    assert (PACKAGE_ROOT / "urdf" / "warehouse_drone.urdf").is_file()
    assert (PACKAGE_ROOT / "config" / "gazebo_bridge.yaml").is_file()


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

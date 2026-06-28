from __future__ import annotations

import ast
from pathlib import Path


ROS_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "fatal"}
ROS_SOURCE_ROOTS = (
    Path("backend/modules/warehouse/service"),
    Path("ros2_ws/src/drone_gz_bridge/drone_gz_bridge"),
)


def _ros_logger_call(node: ast.Call) -> ast.Attribute | None:
    function = node.func
    if not isinstance(function, ast.Attribute):
        return None
    receiver = function.value
    if not isinstance(receiver, ast.Call):
        return None
    getter = receiver.func
    if not isinstance(getter, ast.Attribute) or getter.attr != "get_logger":
        return None
    return function


def test_ros_logger_calls_use_the_rcutils_contract() -> None:
    violations: list[str] = []
    for root in ROS_SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = _ros_logger_call(node)
                if function is None:
                    continue
                if function.attr == "exception":
                    violations.append(f"{path}:{node.lineno}: exception is unsupported")
                elif function.attr in ROS_LOG_METHODS and len(node.args) != 1:
                    violations.append(
                        f"{path}:{node.lineno}: {function.attr} expects one message argument"
                    )

    assert violations == []


def test_colored_bridge_subscribes_before_publishers_are_ready() -> None:
    from backend.modules.warehouse.service.colored_pointcloud_live_map_bridge import (
        _sources_with_late_publisher_fallbacks,
    )

    sources, missing = _sources_with_late_publisher_fallbacks(
        {},
        ("rgbd_colored", "nvblox_esdf"),
    )

    assert missing == {"rgbd_colored", "nvblox_esdf"}
    assert sources["rgbd_colored"].topic == "/warehouse/front/rgbd/points"
    assert sources["nvblox_esdf"].topic == "/nvblox_node/static_esdf_pointcloud"


def test_embedded_ros_uses_the_same_transport_as_cli_probes(monkeypatch) -> None:
    from backend.infrastructure.warehouse.bridge_config import (
        configure_embedded_ros_environment,
    )

    monkeypatch.delenv("FASTDDS_BUILTIN_TRANSPORTS", raising=False)
    monkeypatch.delenv("ROS_DOMAIN_ID", raising=False)
    configure_embedded_ros_environment()

    assert __import__("os").environ["FASTDDS_BUILTIN_TRANSPORTS"] == "UDPv4"
    assert __import__("os").environ["ROS_DOMAIN_ID"] == "0"


def test_live_map_storage_calls_include_coordinate_frame() -> None:
    violations: list[str] = []
    root = Path("backend/modules/warehouse")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute) or function.attr != "save_upload":
                continue
            if not any(keyword.arg == "frame_id" for keyword in node.keywords):
                violations.append(f"{path}:{node.lineno}")

    assert violations == []


def test_embedded_live_map_nodes_use_simulation_time() -> None:
    bridge_files = (
        Path("backend/modules/warehouse/service/colored_pointcloud_live_map_bridge.py"),
        Path("backend/modules/warehouse/service/raw_pointcloud_live_map_bridge.py"),
        Path("backend/modules/warehouse/service/nvblox_layers_live_map_bridge.py"),
    )
    for path in bridge_files:
        source = path.read_text(encoding="utf-8")
        assert 'Parameter("use_sim_time", value=True)' in source, str(path)

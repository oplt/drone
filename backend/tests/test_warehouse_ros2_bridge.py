from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SRC = ROOT / "warehouse_ros2_ws" / "src" / "warehouse_mapping_bridge"
if str(BRIDGE_SRC) not in sys.path:
    sys.path.insert(0, str(BRIDGE_SRC))

from warehouse_mapping_bridge.config import BridgeConfig, topic_env  # noqa: E402
from warehouse_mapping_bridge.session import BridgeState  # noqa: E402


def _config(tmp_path: Path) -> BridgeConfig:
    return BridgeConfig(
        host="127.0.0.1",
        port=8088,
        capture_root=tmp_path,
        profile="isaac_ros_nvblox_stereo",
        ros_ws_url="ws://jetson.test/ws",
        autolaunch=False,
        launch_cmd="ros2 launch warehouse_mapping_bridge isaac_warehouse_mapping.launch.py",
        mavlink_vision_url="udpout:127.0.0.1:14550",
        odometry_state_path=tmp_path / "latest_odometry.json",
    )


def test_bridge_start_stop_writes_capture_bundle(tmp_path: Path) -> None:
    state = BridgeState(_config(tmp_path))

    started = state.start_mapping(
        {
            "flight_id": "flight:42",
            "warehouse_map_id": 7,
            "metadata": {"operator": "test"},
            "calibration": {"hash": "abc"},
        }
    )

    assert started["accepted"] is True
    data = started["data"]
    assert isinstance(data, dict)
    session_dir = Path(data["session_dir"])
    assert session_dir.name == "flight_flight_42"
    assert (session_dir / "warehouse_mapping_manifest.json").exists()
    assert (session_dir / "capture_metadata.json").exists()
    assert (session_dir / "mapping_health_summary.json").exists()

    stopped = state.stop_mapping("flight:42")

    assert stopped["status"] == "stopped"
    assert (session_dir / "artifact_index.json").exists()


def test_bridge_download_artifacts_copies_bundle(tmp_path: Path) -> None:
    state = BridgeState(_config(tmp_path / "capture"))
    state.start_mapping({"flight_id": "99", "warehouse_map_id": 3})
    state.stop_mapping("99")

    destination = tmp_path / "downloaded"
    result: dict[str, Any] = state.download_artifacts("99", destination)

    assert result["status"] == "downloaded"
    assert (destination / "warehouse_mapping_manifest.json").exists()
    assert (destination / "capture_metadata.json").exists()
    assert len(result["paths"]) >= 3


def test_bridge_topic_env_includes_nvblox_visualization_topics() -> None:
    topics = topic_env()

    assert topics["rgb_image"] == "/warehouse/front/rgbd/image"
    assert topics["raw_lidar"] == "/lidar/points"
    assert topics["occupancy"] == "/nvblox_node/occupancy_layer"
    assert topics["esdf"] == "/nvblox_node/static_esdf_pointcloud"
    assert topics["mesh_marker"] == "/nvblox_node/mesh_marker"

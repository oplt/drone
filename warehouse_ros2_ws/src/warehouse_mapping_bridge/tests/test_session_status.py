from __future__ import annotations

from warehouse_mapping_bridge.config import BridgeConfig
from warehouse_mapping_bridge.session import BridgeState
from warehouse_mapping_bridge.session_model import MappingSession, write_json


def _state(tmp_path) -> BridgeState:
    return BridgeState(
        BridgeConfig(
            host="127.0.0.1",
            port=8088,
            capture_root=tmp_path,
            profile="gazebo",
            ros_ws_url="",
            autolaunch=False,
            launch_cmd="true",
            mavlink_vision_url="",
            odometry_state_path=tmp_path / "odometry.json",
        )
    )


def test_mapping_status_lists_active_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_HEALTH_BACKGROUND_PROBE", "0")
    state = _state(tmp_path)
    session = MappingSession(
        flight_id="flight_1",
        warehouse_map_id=7,
        profile="gazebo",
        session_dir=tmp_path / "flight_flight_1",
    )
    state.sessions[session.flight_id] = session

    status = state.mapping_status()

    assert status["accepted"] is True
    assert status["data"]["active_count"] == 1
    assert status["data"]["sessions"][0]["flight_id"] == "flight_1"


def test_mapping_status_reads_stopped_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WAREHOUSE_HEALTH_BACKGROUND_PROBE", "0")
    state = _state(tmp_path)
    session_dir = tmp_path / "flight_abc"
    write_json(
        session_dir / "warehouse_mapping_manifest.json",
        {"flight_id": "abc", "status": "stopped", "profile": "gazebo"},
    )

    status = state.mapping_status("abc")

    assert status["accepted"] is True
    assert status["status"] == "stopped"
    assert status["data"]["process_alive"] is False

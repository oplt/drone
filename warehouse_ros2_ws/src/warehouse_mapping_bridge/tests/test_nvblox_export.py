from __future__ import annotations

from pathlib import Path
from unittest import mock

from warehouse_mapping_bridge import nvblox_export


def test_record_snapshot_on_stop_default_for_gazebo() -> None:
    with mock.patch.dict("os.environ", {}, clear=True):
        assert nvblox_export.record_snapshot_on_stop_enabled(profile="gazebo") is True
        assert nvblox_export.record_snapshot_on_stop_enabled(profile="isaac_ros_nvblox_stereo") is False


def test_export_nvblox_artifacts_calls_save_ply(tmp_path: Path) -> None:
    session_dir = tmp_path / "flight_9"
    session_dir.mkdir()
    mesh_path = session_dir / "artifacts" / "mesh.ply"

    def fake_call(service_name: str, file_path: Path, *, timeout_s: float = 30.0) -> bool:
        if service_name == "/nvblox_node/save_ply":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("ply", encoding="utf-8")
            return True
        return False

    with mock.patch.object(nvblox_export, "call_filepath_service", side_effect=fake_call):
        count = nvblox_export.export_nvblox_artifacts(
            session_dir,
            listed_topics={"/nvblox_node/mesh"},
            profile="gazebo",
        )
    assert count >= 1
    assert mesh_path.is_file()

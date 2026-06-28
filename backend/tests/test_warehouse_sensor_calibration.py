from pathlib import Path

import pytest
import yaml

from backend.modules.warehouse.service.sensor_calibration import (
    REQUIRED_FRAME_EDGES,
    normalize_sensor_extrinsics,
    sensor_calibration_checksum,
)

CALIBRATION_FILE = (
    Path(__file__).parents[2] / "ros2_ws/src/drone_gz_bridge/config/sensor_extrinsics.yaml"
)


def _calibration() -> dict:
    return yaml.safe_load(CALIBRATION_FILE.read_text(encoding="utf-8"))


def test_ros_calibration_uses_exact_stable_frame_tree() -> None:
    normalized = normalize_sensor_extrinsics(_calibration())
    edges = {(item["parent_frame"], item["child_frame"]) for item in normalized["transforms"]}

    assert edges == REQUIRED_FRAME_EDGES
    assert len(sensor_calibration_checksum(normalized)) == 64


def test_duplicate_child_frame_is_rejected() -> None:
    payload = _calibration()
    payload["transforms"][1]["child_frame"] = "lidar_link"

    with pytest.raises(ValueError, match="invalid or duplicate"):
        normalize_sensor_extrinsics(payload)


def test_non_unit_extrinsic_rotation_is_rejected() -> None:
    payload = _calibration()
    payload["transforms"][0]["rotation"]["w"] = 2.0

    with pytest.raises(ValueError, match="normalized"):
        normalize_sensor_extrinsics(payload)

from types import SimpleNamespace

import pytest

from backend.modules.warehouse.service.frame_contract import (
    CALIBRATED_FRAME_EDGES,
    FRAME_DEFINITIONS,
    REQUIRED_FRAME_EDGES,
    frame_contract_payload,
    validate_frame_tree,
)


def test_canonical_frame_tree_is_complete_and_acyclic() -> None:
    assert validate_frame_tree(set(REQUIRED_FRAME_EDGES)) == set(REQUIRED_FRAME_EDGES)
    frame_ids = {frame.frame_id for frame in FRAME_DEFINITIONS}
    assert {
        "warehouse_map",
        "odom",
        "base_link",
        "lidar_link",
        "camera_link",
        "camera_optical_frame",
        "rgbd_link",
        "imu_link",
        "gimbal_link",
        "dock",
    } <= frame_ids
    assert ("camera_link", "camera_optical_frame") in CALIBRATED_FRAME_EDGES
    assert ("base_link", "gimbal_link") not in CALIBRATED_FRAME_EDGES


def test_frame_tree_rejects_missing_duplicate_parent_and_unknown_edges() -> None:
    with pytest.raises(ValueError, match="missing"):
        validate_frame_tree(set(REQUIRED_FRAME_EDGES) - {("odom", "base_link")})
    with pytest.raises(ValueError, match="one parent"):
        validate_frame_tree([*REQUIRED_FRAME_EDGES, ("camera_link", "imu_link")])
    with pytest.raises(ValueError, match="unregistered"):
        validate_frame_tree([*REQUIRED_FRAME_EDGES, ("base_link", "foo_link")])


def test_frame_contract_is_checksumed_and_revisioned() -> None:
    frame = SimpleNamespace(
        id=7,
        version=3,
        parent_frame_id="warehouse_map",
        child_frame_id="odom",
        status="locked",
        transform_json={
            "translation": {"x": 1, "y": 2, "z": 0},
            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
        },
    )
    payload = frame_contract_payload(coordinate_frame=frame)

    assert len(payload["checksum_sha256"]) == 64
    assert payload["active_revision"]["id"] == 7
    assert payload["active_revision"]["version"] == 3

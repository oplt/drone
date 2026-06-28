from __future__ import annotations

import math

import numpy as np
import pytest

from backend.modules.warehouse.planning.mission_stages import normalize_mission_stage
from backend.modules.warehouse.service.esdf_inspection_validation import (
    validate_inspection_path_esdf,
)
from backend.modules.warehouse.service.floor_plane_ransac import fit_floor_plane_ransac
from backend.modules.warehouse.service.gazebo_landmark_consistency import (
    LandmarkObservation,
    LandmarkSpec,
    evaluate_landmark_consistency,
)
from backend.modules.warehouse.service.provisional_mapping import (
    begin_provisional_epoch,
    block_executable_mission,
    map_candidate_status,
    note_provisional_update,
    provisional_epoch_snapshot,
)
from backend.modules.warehouse.service.scan_odom_alignment import estimate_scan_odom_to_warehouse_map
from backend.modules.warehouse.service.slam_localization_monitor import (
    slam_localization_snapshot,
    update_slam_localization,
)
from backend.modules.vehicle_runtime.local_position_adapter import MavlinkLocalPositionAdapter
from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid


def test_floor_plane_ransac_finds_horizontal_plane() -> None:
    rng = np.random.default_rng(0)
    plane = np.column_stack(
        [
            rng.uniform(0, 10, 200),
            rng.uniform(0, 10, 200),
            rng.normal(0.0, 0.01, 200),
        ]
    )
    result = fit_floor_plane_ransac(plane)
    assert result["ok"] is True
    assert float(result["inlier_ratio"]) > 0.8


def test_scan_odom_alignment_from_floor_plane() -> None:
    floor = {
        "ok": True,
        "centroid_m": [1.0, 2.0, 0.0],
        "dominant_yaw_rad": 0.0,
        "residual_rms_m": 0.01,
        "inlier_ratio": 0.9,
    }
    aligned = estimate_scan_odom_to_warehouse_map(floor_plane=floor)
    assert aligned["ok"] is True
    assert aligned["child_frame"] == "scan_odom"


def test_landmark_consistency_within_tolerance() -> None:
    identity = {
        "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    }
    report = evaluate_landmark_consistency(
        landmarks=[LandmarkSpec("dock", 1.0, 2.0, 0.0)],
        observations=[LandmarkObservation("dock", 1.0, 2.0, 0.0)],
        map_to_odom=identity,
    )
    assert report["passed"] is True


def test_provisional_epoch_revisioning() -> None:
    begin_provisional_epoch(warehouse_map_id=99, epoch_id="scan-1")
    note_provisional_update(warehouse_map_id=99, confidence=0.8)
    snapshot = provisional_epoch_snapshot(99)
    assert snapshot is not None
    assert snapshot["revision"] == 1
    assert snapshot["confidence"] == 0.8


def test_block_executable_mission_for_provisional_slam() -> None:
    assert block_executable_mission(
        coordinate_frame_status="locked",
        localization_method="live_slam",
    )
    assert not block_executable_mission(
        coordinate_frame_status="locked",
        localization_method="operator",
    )


def test_map_candidate_status_mapping() -> None:
    assert map_candidate_status("accepted") == "confirmed"


def test_slam_localization_snapshot_healthy_after_update() -> None:
    update_slam_localization(confidence=0.9, transform={"translation": {"x": 0, "y": 0, "z": 0}})
    snapshot = slam_localization_snapshot()
    assert snapshot["healthy"] is True


def test_mavlink_local_position_adapter_en_ned() -> None:
    from backend.modules.vehicle_runtime.types import EnuCoordinate

    adapter = MavlinkLocalPositionAdapter()
    enu = EnuCoordinate(x_m=3.0, y_m=4.0, z_m=2.0, yaw_deg=90.0)
    local = adapter.enu_path_to_local_ned([enu])[0]
    assert math.isclose(local.north_m, 4.0)
    assert math.isclose(local.east_m, 3.0)
    assert math.isclose(local.down_m, -2.0)


def test_mission_stage_normalization() -> None:
    assert normalize_mission_stage("approach_target") == "approach"
    assert normalize_mission_stage("localize") == "localize"


def test_esdf_validation_fallback_to_occupancy() -> None:
    grid = OccupancyGrid(resolution_m=1.0, width=4, height=4, default_state="free")
    poses = [LocalPose(x_m=1.5, y_m=1.5, z_m=1.0, frame_id="warehouse_map")]
    grid_poses = [LocalPose(x_m=1.5, y_m=1.5, z_m=1.0, frame_id="odom")]
    report = validate_inspection_path_esdf(
        poses=poses,
        esdf_points_xyz=None,
        grid=grid,
        grid_poses=grid_poses,
    )
    assert report["passed"] is True
    assert any(item.get("check") == "esdf_unavailable" for item in report["warnings"])


def test_gazebo_landmark_consistency_rejects_large_offset() -> None:
    identity = {
        "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    }
    report = evaluate_landmark_consistency(
        landmarks=[LandmarkSpec("dock", 1.0, 2.0, 0.0)],
        observations=[LandmarkObservation("dock", 4.0, 2.0, 0.0)],
        map_to_odom=identity,
    )
    assert report["passed"] is False


@pytest.mark.asyncio
async def test_localization_runtime_gate_flags_stale_slam(monkeypatch) -> None:
    from backend.modules.warehouse.service.inspection_execution_gate import localization_runtime_gate

    async def _noop_probe(**_kwargs):
        return {"ingested": False}

    monkeypatch.setattr(
        "backend.modules.warehouse.service.inspection_execution_gate.refresh_slam_localization_from_ros",
        _noop_probe,
    )
    monkeypatch.setattr(
        "backend.modules.warehouse.service.inspection_execution_gate.slam_localization_snapshot",
        lambda **_: {"healthy": False, "confidence": 0.1, "age_ms": 5000.0},
    )
    reason = await localization_runtime_gate("live_slam", probe_ros=True)
    assert reason == "localization_unhealthy"
    assert await localization_runtime_gate("operator", probe_ros=False) is None

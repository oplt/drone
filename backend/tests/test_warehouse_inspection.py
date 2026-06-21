from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from backend.modules.missions.flight_profile import flight_profile_for_mission_type
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.planning.indoor.enums import OccupancyState
from backend.modules.warehouse.planning.indoor.models import OccupancyGrid
from backend.modules.warehouse.schemas import WarehouseLocalPoint, WarehouseScanTargetCreate
from backend.modules.warehouse.service.inspection import (
    MockWarehouseScanner,
    build_inspection_waypoints,
    compute_scan_pose,
    order_targets,
)
from backend.modules.warehouse.service.structure_extraction import (
    GeneratedTarget,
    StructureResult,
    _assign_astar_priority,
    _detect_shelf_levels,
    classify_clearance,
)
from backend.modules.warehouse.service.structure_jobs import (
    _attach_quality_gate,
    ensure_structure_quality_summary,
)


def _target(
    target_id: int,
    *,
    x_m: float,
    priority: int = 100,
    map_id: int = 1,
) -> WarehouseScanTarget:
    return WarehouseScanTarget(
        id=target_id,
        warehouse_map_id=map_id,
        aisle_code="A-01",
        rack_code="R-01",
        bin_code=f"B-{target_id}",
        barcode=f"CODE-{target_id}",
        target_point_local_json={
            "frame_id": "warehouse_map",
            "x_m": x_m + 1.2,
            "y_m": 0.0,
            "z_m": 1.5,
        },
        scan_pose_local_json={
            "frame_id": "warehouse_map",
            "x_m": x_m,
            "y_m": 0.0,
            "z_m": 1.5,
            "yaw_deg": 0.0,
        },
        standoff_m=1.2,
        hover_time_s=3.0,
        scan_timeout_s=8.0,
        priority=priority,
        active=True,
    )


def test_warehouse_inspection_uses_indoor_local_profile() -> None:
    profile = flight_profile_for_mission_type(MissionType.WAREHOUSE_INSPECTION)

    assert profile.requires_gps_home is False
    assert profile.control_mode == "local_setpoint"


def test_scan_target_requires_matching_frames() -> None:
    with pytest.raises(ValidationError):
        WarehouseScanTargetCreate.model_validate(
            {
                "aisle_code": "A-01",
                "target_point_local_json": {
                    "frame_id": "warehouse_map",
                    "x_m": 1.0,
                    "y_m": 2.0,
                    "z_m": 1.5,
                },
                "scan_pose_local_json": {
                    "frame_id": "odom",
                    "x_m": 0.0,
                    "y_m": 2.0,
                    "z_m": 1.5,
                    "yaw_deg": 90.0,
                },
            }
        )


def test_scan_pose_computed_from_shelf_normal() -> None:
    pose = compute_scan_pose(
        target_point=WarehouseLocalPoint(x_m=12.8, y_m=4.2, z_m=1.7),
        shelf_normal=None,
        standoff_m=1.2,
        yaw_deg=90.0,
    )

    assert pose.frame_id == "warehouse_map"
    assert pose.x_m == 12.8
    assert pose.yaw_deg == 90.0


def test_mission_waypoints_use_scan_pose_not_target_point() -> None:
    target = _target(1, x_m=11.6)

    waypoints = build_inspection_waypoints([target])

    assert [waypoint.purpose for waypoint in waypoints] == [
        "navigate_to_scan_pose",
        "hover_for_scan",
        "trigger_barcode_scan",
        "record_result",
    ]
    assert waypoints[0].pose.x_m == 11.6
    assert waypoints[0].pose.x_m != target.target_point_local_json["x_m"]


def test_nearest_neighbor_ordering_after_priority_sort() -> None:
    targets = [
        _target(1, x_m=0.0, priority=100),
        _target(2, x_m=20.0, priority=100),
        _target(3, x_m=2.0, priority=100),
    ]

    ordered = order_targets(targets, optimize_order=True)

    assert [target.id for target in ordered] == [1, 3, 2]


def test_structure_targets_use_occupancy_astar_priority() -> None:
    grid = OccupancyGrid(
        resolution_m=1.0,
        width=6,
        height=5,
        default_state=OccupancyState.FREE,
    )
    for y_idx in range(1, 5):
        grid.set_cell(2, y_idx, OccupancyState.OCCUPIED)

    def generated(bin_code: str, x_m: float, y_m: float) -> GeneratedTarget:
        pose = {
            "frame_id": "warehouse_map",
            "x_m": x_m,
            "y_m": y_m,
            "z_m": 1.0,
            "yaw_deg": 0.0,
        }
        return GeneratedTarget(
            aisle_code="A1",
            rack_code="R1",
            shelf_level=0,
            bin_code=bin_code,
            target_point=pose,
            shelf_normal={"frame_id": "warehouse_map", "x": 1.0, "y": 0.0, "z": 0.0},
            scan_pose=pose,
            standoff_m=1.2,
            priority=100,
        )

    start = generated("B1", 0.5, 2.5)
    blocked_near = generated("B2", 3.5, 2.5)
    same_side = generated("B3", 0.5, 4.5)

    _assign_astar_priority([start, blocked_near, same_side], occupancy_grid=grid, clearance_m=0.0)

    assert same_side.priority == 1
    assert blocked_near.priority == 2


def test_structure_quality_gate_drafts_noisy_pointcloud_fallback() -> None:
    result = StructureResult(
        targets=[],
        summary={
            "counts": {
                "aisles": 1,
                "racks": 7,
                "targets": 198,
                "rejected_clearance": 185,
            },
            "clearance": {"source": "point_cloud_fallback"},
            "map_quality": {
                "chunk_counts": {"rgbd_colored": 127, "mid360_raw": 48, "nvblox_esdf": 40},
                "point_counts": {"rgbd_colored": 2_626_723, "mid360_raw": 301_863, "nvblox_esdf": 2_103},
                "missing_topics": [],
            },
        },
        rejected_clearance=185,
    )

    _attach_quality_gate(result)

    quality = result.summary["quality"]
    assert quality["status"] == "needs_review"
    assert quality["active_target_count"] == 0
    assert "missing_occupancy_grid" in quality["reasons"]
    assert "too_many_targets_per_rack" in quality["reasons"]
    assert "clearance_rejection_ratio_high" in quality["reasons"]
    assert "weak_esdf" in quality["reasons"]


def test_structure_quality_gate_accepts_occupancy_backed_output() -> None:
    result = StructureResult(
        targets=[],
        summary={
            "counts": {
                "aisles": 2,
                "racks": 8,
                "targets": 64,
                "rejected_clearance": 4,
            },
            "clearance": {"source": "occupancy_grid"},
            "map_quality": {
                "chunk_counts": {"nvblox_occupancy": 1, "nvblox_esdf": 40},
                "point_counts": {"nvblox_esdf": 25_000},
                "missing_topics": [],
            },
        },
        rejected_clearance=4,
    )

    _attach_quality_gate(result)

    quality = result.summary["quality"]
    assert quality["status"] == "ready"
    assert quality["active_target_count"] == 64
    assert quality["reasons"] == []


def test_structure_quality_trusts_live_esdf_occupancy_diagnostics() -> None:
    """Regression: live ROS readiness must suppress false missing_* reasons.

    The point cloud clearance fallback and a missing ``nvblox_occupancy`` chunk
    used to force ``missing_occupancy_grid`` / ``missing_esdf_topic``. When the
    fresh extraction-time readiness probe confirms the topics publish, those
    reasons must not appear.
    """
    result = StructureResult(
        targets=[],
        summary={
            "counts": {
                "aisles": 2,
                "racks": 6,
                "candidate_targets": 64,
                "active_targets": 0,
                "rejected_clearance": 8,
            },
            "clearance": {"source": "point_cloud_kdtree"},
            "diagnostics": {
                "esdf_available": True,
                "esdf_topic": "/nvblox_node/static_esdf_pointcloud",
                "occupancy_available": True,
                "occupancy_topic": "/nvblox_node/combined_occupancy_grid",
            },
            "map_quality": {
                "chunk_counts": {"rgbd_colored": 64},
                "missing_topics": ["/nvblox_node/static_esdf_pointcloud"],
            },
        },
        rejected_clearance=8,
    )

    _attach_quality_gate(result)

    reasons = result.summary["quality"]["reasons"]
    assert "missing_esdf_topic" not in reasons
    assert "missing_occupancy_grid" not in reasons


def test_classify_clearance_status_thresholds() -> None:
    strict = 0.25
    review = 0.10

    # Strict pass with reliable evidence -> active.
    assert (
        classify_clearance(
            0.30, strict_clearance_m=strict, review_clearance_m=review, reliable_evidence=True
        )
        == "active"
    )
    # Strict pass but no reliable clearance evidence -> needs_review (soft).
    assert (
        classify_clearance(
            0.30, strict_clearance_m=strict, review_clearance_m=review, reliable_evidence=False
        )
        == "needs_review"
    )
    # Between review and strict -> needs_review.
    assert (
        classify_clearance(
            0.15, strict_clearance_m=strict, review_clearance_m=review, reliable_evidence=True
        )
        == "needs_review"
    )
    # Below review threshold -> rejected.
    assert (
        classify_clearance(
            0.05, strict_clearance_m=strict, review_clearance_m=review, reliable_evidence=True
        )
        == "rejected"
    )


def test_structure_quality_backfills_legacy_summary() -> None:
    summary = {
        "counts": {
            "aisles": 1,
            "racks": 7,
            "targets": 198,
            "rejected_clearance": 185,
        },
        "clearance": {"source": "point_cloud_kdtree"},
        "map_quality": {
            "chunk_counts": {"nvblox_esdf": 40, "rgbd_colored": 127},
            "missing_topics": ["/nvblox_node/static_esdf_pointcloud"],
        },
    }

    ensure_structure_quality_summary(summary)

    assert summary["quality"]["status"] == "needs_review"
    assert summary["quality"]["active_target_count"] == 0


def _synthetic_two_rack_warehouse_cloud() -> np.ndarray:
    """Build a deterministic two-rack / one-aisle point cloud for extraction."""
    rng = np.random.default_rng(7)
    parts: list[np.ndarray] = []

    # Floor slab so floor detection has a clear z=0 plane.
    fx = rng.uniform(0.0, 8.0, 6000)
    fy = rng.uniform(-0.5, 4.0, 6000)
    fz = np.zeros_like(fx)
    parts.append(np.column_stack([fx, fy, fz]))

    # Two dense rack rows (vertical mass) separated by a wide empty aisle.
    for y_lo, y_hi in ((0.0, 0.4), (3.0, 3.4)):
        rx = rng.uniform(0.0, 8.0, 9000)
        ry = rng.uniform(y_lo, y_hi, 9000)
        rz = rng.uniform(0.3, 3.0, 9000)
        parts.append(np.column_stack([rx, ry, rz]))

    return np.ascontiguousarray(np.vstack(parts).astype(np.float32))


def test_extract_structure_creates_draft_setup_without_active_targets() -> None:
    from backend.modules.warehouse.service.structure_extraction import (
        StructureExtractionParams,
        extract_structure,
    )

    cloud = _synthetic_two_rack_warehouse_cloud()

    # No occupancy grid -> no reliable clearance evidence -> nothing is promoted
    # to "active", so the run must still yield a reviewable draft setup instead of
    # raising or silently returning nothing.
    result = extract_structure(
        cloud,
        params=StructureExtractionParams(axis_deg=0.0).sanitized(),
        occupancy_grid=None,
    )

    summary = result.summary
    counts = summary["target_counts"]

    assert counts["candidate"] > 0
    assert counts["active"] == 0
    assert counts["candidate"] == counts["active"] + counts["needs_review"] + counts["rejected"]
    assert summary["coordinate_setup_status"] == "draft"
    assert summary["manual_review_required"] is True
    assert summary["counts"]["racks"] >= 1
    assert {t.clearance_status for t in result.targets} <= {
        "active",
        "needs_review",
        "rejected",
    }


def test_shelf_detection_caps_noisy_vertical_peaks() -> None:
    import numpy as np

    z = np.concatenate(
        [np.full(20, level, dtype=np.float32) for level in np.linspace(0.4, 5.8, 19)]
    )

    levels = _detect_shelf_levels(z, spacing=0.25, res=0.1, max_levels=6)

    assert 1 <= len(levels) <= 6


@pytest.mark.asyncio
async def test_mock_scanner_returns_expected_barcode() -> None:
    result = await MockWarehouseScanner().scan_target(_target(4, x_m=0.0), timeout_s=8.0)

    assert result.status == "success"
    assert result.detected_barcode == "CODE-4"

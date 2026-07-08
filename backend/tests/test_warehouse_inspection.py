from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from backend.modules.missions.flight_profile import flight_profile_for_mission_type
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.warehouse.models import WarehouseInspectionResult, WarehouseScanTarget
from backend.modules.warehouse.planning.indoor.enums import OccupancyState
from backend.modules.warehouse.planning.indoor.models import OccupancyGrid
from backend.modules.warehouse.schemas import (
    WarehouseLocalPoint,
    WarehouseLocalPose,
    WarehouseScanTargetCreate,
)
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


def test_scan_target_rejects_arbitrary_matching_frames() -> None:
    with pytest.raises(ValidationError, match="warehouse_map"):
        WarehouseScanTargetCreate.model_validate(
            {
                "aisle_code": "A-01",
                "target_point_local_json": {
                    "frame_id": "foo",
                    "x_m": 1,
                    "y_m": 2,
                    "z_m": 1.5,
                },
                "scan_pose_local_json": {
                    "frame_id": "foo",
                    "x_m": 0,
                    "y_m": 2,
                    "z_m": 1.5,
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


def test_pose_canonicalizes_legacy_yaw_to_quaternion_and_derived_euler() -> None:
    pose = WarehouseLocalPose(x_m=1, y_m=2, z_m=3, yaw_deg=90)

    assert pose.frame_id == "warehouse_map"
    assert pose.orientation.z == pytest.approx(2**-0.5)
    assert pose.orientation.w == pytest.approx(2**-0.5)
    assert pose.roll_deg == pytest.approx(0)
    assert pose.pitch_deg == pytest.approx(0)
    assert pose.yaw_deg == pytest.approx(90)


def test_scan_target_keeps_sensor_aim_separate_from_vehicle_pose() -> None:
    target = WarehouseScanTargetCreate.model_validate(
        {
            "aisle_code": "A-01",
            "target_point_local_json": {"x_m": 2, "y_m": 0, "z_m": 1},
            "scan_pose_local_json": {"x_m": 1, "y_m": 0, "z_m": 1, "yaw_deg": 0},
            "sensor_aim_json": {
                "sensor_frame_id": "gimbal_camera_optical_frame",
                "aim_point_local_json": {"x_m": 2, "y_m": 0, "z_m": 0.5},
                "pitch_deg": -25,
                "roll_deg": 5,
            },
        }
    )

    assert target.scan_pose_local_json.pitch_deg == 0
    assert target.sensor_aim_json is not None
    assert target.sensor_aim_json.pitch_deg == pytest.approx(-25)
    assert target.sensor_aim_json.roll_deg == pytest.approx(5)


def test_mission_waypoints_use_scan_pose_not_target_point() -> None:
    target = _target(1, x_m=11.6)
    target.sku = "SKU-1"
    target.scanner_metadata_json = {
        "barcode_mode": "decode",
        "empty_bin_vision_mode": "classify_empty_bin",
        "image_roi": {"mode": "center_crop", "x": 0.25, "y": 0.2, "width": 0.5, "height": 0.6},
        "min_confidence": 0.8,
    }

    waypoints = build_inspection_waypoints([target])

    assert [waypoint.purpose for waypoint in waypoints] == [
        "approach_target",
        "hover_for_scan",
        "trigger_scan",
        "exit_target",
    ]
    assert waypoints[1].pose.x_m == 11.6
    assert waypoints[1].pose.x_m != target.target_point_local_json["x_m"]
    assert waypoints[2].metadata["barcode_mode"] == "decode"
    assert waypoints[2].metadata["empty_bin_vision_mode"] == "classify_empty_bin"
    assert waypoints[2].metadata["expected_sku"] == "SKU-1"
    assert waypoints[2].metadata["min_confidence"] == 0.8


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
                "point_counts": {
                    "rgbd_colored": 2_626_723,
                    "mid360_raw": 301_863,
                    "nvblox_esdf": 2_103,
                },
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


def _rotate_cloud_z(cloud: np.ndarray, degrees: float) -> np.ndarray:
    theta = math.radians(float(degrees))
    rotation = np.array(
        [
            [math.cos(theta), -math.sin(theta), 0.0],
            [math.sin(theta), math.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    return np.ascontiguousarray(cloud @ rotation.T)


def _partial_occlusion_cloud(cloud: np.ndarray) -> np.ndarray:
    keep = ~((cloud[:, 0] > 3.0) & (cloud[:, 0] < 4.5) & (cloud[:, 2] > 0.2))
    return np.ascontiguousarray(cloud[keep])


def _asymmetric_rack_depth_cloud() -> np.ndarray:
    rng = np.random.default_rng(9)
    parts: list[np.ndarray] = []
    floor_x = rng.uniform(0.0, 8.0, 6000)
    floor_y = rng.uniform(-0.5, 4.0, 6000)
    parts.append(np.column_stack([floor_x, floor_y, np.zeros_like(floor_x)]))
    for y_lo, y_hi, count in ((0.0, 0.25, 9000), (3.0, 3.7, 12000)):
        parts.append(
            np.column_stack(
                [
                    rng.uniform(0.0, 8.0, count),
                    rng.uniform(y_lo, y_hi, count),
                    rng.uniform(0.3, 3.0, count),
                ]
            )
        )
    return np.ascontiguousarray(np.vstack(parts).astype(np.float32))


def _noisy_floor_ceiling_cloud(cloud: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(11)
    noisy = cloud.copy()
    floor = noisy[:, 2] == 0.0
    noisy[floor, 2] = rng.normal(0.0, 0.02, int(floor.sum()))
    ceiling = np.column_stack(
        [
            rng.uniform(0.0, 8.0, 4000),
            rng.uniform(-0.5, 4.0, 4000),
            rng.normal(3.2, 0.03, 4000),
        ]
    )
    return np.ascontiguousarray(np.vstack([noisy, ceiling]).astype(np.float32))


@pytest.mark.parametrize(
    ("case_name", "cloud_factory", "axis_deg", "params_kwargs"),
    [
        ("straight_aisles", lambda base: base, 0.0, {}),
        ("rotated_aisles", lambda base: _rotate_cloud_z(base, 30.0), 30.0, {}),
        ("partial_occlusion", _partial_occlusion_cloud, 0.0, {}),
        ("asymmetric_rack_depths", lambda _base: _asymmetric_rack_depth_cloud(), 0.0, {}),
        ("noisy_floor_ceiling", _noisy_floor_ceiling_cloud, 0.0, {}),
        (
            "missing_shelf_levels_template_prior",
            lambda base: np.ascontiguousarray(base[base[:, 2] < 2.0]),
            0.0,
            {
                "rack_template_bay_width_m": 2.0,
                "rack_template_bin_count": 2,
                "rack_template_shelf_levels_m": (0.75, 1.5, 2.25),
            },
        ),
    ],
)
def test_category10_geometry_extraction_synthetic_warehouses(
    case_name: str,
    cloud_factory,
    axis_deg: float,
    params_kwargs: dict,
) -> None:
    from backend.modules.warehouse.service.structure_extraction import (
        StructureExtractionParams,
        extract_structure,
    )

    cloud = cloud_factory(_synthetic_two_rack_warehouse_cloud())

    result = extract_structure(
        cloud,
        params=StructureExtractionParams(axis_deg=axis_deg, **params_kwargs).sanitized(),
        occupancy_grid=None,
    )

    assert result.targets, case_name
    assert result.summary["counts"]["aisles"] >= 1
    assert result.summary["counts"]["racks"] >= 1
    assert result.summary["target_counts"]["candidate"] == len(result.targets)
    assert result.summary["algorithm_core"]["primary"] == "vertical_plane_graph"
    assert result.summary["racks"][0]["face_planes"], case_name
    assert result.summary["racks"][0]["shelf_detection"]["levels_m"], case_name
    if params_kwargs.get("rack_template_shelf_levels_m"):
        assert result.summary["racks"][0]["template_fit"]["applied"] is True


def test_category10_acceptance_thresholds_for_template_backed_extraction() -> None:
    from backend.modules.warehouse.service.structure_extraction import (
        StructureExtractionParams,
        extract_structure,
    )

    params = StructureExtractionParams(
        axis_deg=0.0,
        rack_template_bay_width_m=2.0,
        rack_template_bin_count=2,
        rack_template_shelf_levels_m=(0.75, 1.5),
        max_bins_per_rack_face=8,
    ).sanitized()
    result = extract_structure(
        _synthetic_two_rack_warehouse_cloud(),
        params=params,
        occupancy_grid=None,
    )

    assert result.targets
    for target in result.targets:
        target_z = float(target.target_point["z_m"])
        assert min(abs(target_z - expected) for expected in (0.75, 1.5)) <= 0.10
        normal = target.shelf_normal
        normal_xy_norm = math.hypot(float(normal["x"]), float(normal["y"]))
        assert normal_xy_norm == pytest.approx(1.0, abs=1e-6)
        axis_alignment = abs(float(normal["y"])) / normal_xy_norm
        assert math.degrees(math.acos(min(1.0, axis_alignment))) <= 5.0
        if target.clearance_status == "active":
            assert target.clearance_m is not None
            assert target.clearance_m >= params.required_clearance_m


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
    assert summary["aisle_graph"]["edges"]
    assert summary["algorithm_core"]["primary"] == "vertical_plane_graph"
    assert summary["algorithm_core"]["fallback_used"] is False
    assert summary["rack_plane_clusters"]
    assert summary["racks"][0]["face_planes"]
    assert summary["racks"][0]["face_planes"][0]["source"] == "vertical_plane_extraction"
    assert summary["racks"][0]["shelf_detection"]["source"] == "horizontal_plane_histogram"
    assert "confidence_breakdown" in summary["racks"][0]
    assert "confidence_breakdown" in summary["candidate_targets"][0]
    assert summary["candidate_targets"][0]["scanner_metadata"]["barcode_mode"]
    assert summary["candidate_targets"][0]["path_validation"]["path"]["status"] == "needs_review"
    assert result.targets[0].scanner_metadata["image_roi"]["mode"] == "center_crop"
    assert result.targets[0].path_validation["esdf"]["status"] == "unavailable"
    assert result.targets[0].failure_reason is not None
    assert result.targets[0].standoff_m >= (
        StructureExtractionParams().drone_radius_m + StructureExtractionParams().clearance_margin_m
    )
    assert {t.clearance_status for t in result.targets} <= {
        "active",
        "needs_review",
        "rejected",
    }


def test_extract_structure_replays_stored_flight_chunks_for_known_layout(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.modules.warehouse.service import structure_extraction as extraction
    from backend.modules.warehouse.service.live_map_storage import WarehouseLiveMapChunkStorage

    storage = WarehouseLiveMapChunkStorage(root=tmp_path)
    monkeypatch.setattr(extraction, "warehouse_live_map_chunk_storage", storage)
    flight_id = "known-layout-flight"
    flight_dir = storage.flight_dir(flight_id)
    flight_dir.mkdir(parents=True, exist_ok=True)
    cloud = _synthetic_two_rack_warehouse_cloud()
    (flight_dir / "rgbd_colored_000001-deadbeefdeadbeef.xyz32").write_bytes(
        np.ascontiguousarray(cloud, dtype=np.float32).tobytes()
    )

    result = extraction.extract_structure_from_flight(
        flight_id,
        params=extraction.StructureExtractionParams(axis_deg=0.0).sanitized(),
        odom_to_warehouse_map_transform={
            "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
    )

    assert result.summary["localization_applied"] is True
    assert result.summary["counts"]["racks"] >= 1
    assert result.summary["target_counts"]["candidate"] > 0
    assert result.summary["racks"][0]["shelf_detection"]["levels_m"]


def test_extract_structure_uses_operator_rack_template_overrides() -> None:
    from backend.modules.warehouse.service.structure_extraction import (
        StructureExtractionParams,
        extract_structure,
    )

    cloud = _synthetic_two_rack_warehouse_cloud()

    result = extract_structure(
        cloud,
        params=StructureExtractionParams(
            axis_deg=0.0,
            rack_template_bay_width_m=2.0,
            rack_template_bin_count=2,
            rack_template_shelf_levels_m=(0.75, 1.5),
            max_bins_per_rack_face=8,
        ).sanitized(),
        occupancy_grid=None,
    )

    assert result.targets
    assert {target.bin_code for target in result.targets} <= {"B1", "B2"}
    assert {target.shelf_level for target in result.targets} <= {0, 1}
    assert result.summary["params"]["rack_template_bin_count"] == 2
    assert result.summary["params"]["rack_template_shelf_levels_m"] == [0.75, 1.5]
    assert result.summary["racks"][0]["template_fit"]["applied"] is True
    assert result.summary["candidate_targets"][0]["confidence"] > 0.0


def test_extract_structure_uses_occupancy_free_space_graph() -> None:
    from backend.modules.warehouse.service.structure_extraction import (
        StructureExtractionParams,
        extract_structure,
    )

    cloud = _synthetic_two_rack_warehouse_cloud()
    grid = OccupancyGrid(
        resolution_m=0.5,
        width=20,
        height=12,
        origin_x_m=-1.0,
        origin_y_m=-1.0,
        default_state=OccupancyState.OCCUPIED,
    )
    grid.set_cells(((x, 5) for x in range(2, 18)), OccupancyState.FREE)

    result = extract_structure(
        cloud,
        params=StructureExtractionParams(axis_deg=0.0).sanitized(),
        occupancy_grid=grid,
    )

    assert result.summary["aisle_graph"]["source"] == "occupancy_free_space"
    assert result.summary["routing"]["mode"] == "occupancy_astar"


def test_density_fallback_outputs_require_review(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.modules.warehouse.service import structure_extraction as extraction

    cloud = _synthetic_two_rack_warehouse_cloud()

    def fallback_rows(**_kwargs):
        return [extraction._Band(0.0, 0.4)], [], True

    monkeypatch.setattr(extraction, "_extract_vertical_plane_rows", fallback_rows)

    result = extraction.extract_structure(
        cloud,
        params=extraction.StructureExtractionParams(axis_deg=0.0).sanitized(),
        occupancy_grid=None,
    )

    assert result.summary["algorithm_core"]["fallback_used"] is True
    assert result.targets
    assert {target.clearance_status for target in result.targets} <= {"needs_review", "rejected"}
    assert "fallback_extractor" in result.summary["candidate_targets"][0]["confidence_breakdown"]


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


def test_inspection_feedback_reconstructs_observed_target_and_rescan_waypoints() -> None:
    from backend.modules.warehouse.service.inspection_feedback import (
        observed_target_point,
        rescan_waypoints_for_result,
    )

    target = _target(5, x_m=10.0)
    target.standoff_m = 1.2
    target.shelf_normal_local_json = {
        "frame_id": "warehouse_map",
        "x": 1.0,
        "y": 0.0,
        "z": 0.0,
    }
    target.scan_pose_local_json = {
        "frame_id": "warehouse_map",
        "x_m": 10.0,
        "y_m": 0.0,
        "z_m": 1.5,
        "yaw_deg": 0.0,
    }
    result = WarehouseInspectionResult(
        id=77,
        mission_id=1,
        target_id=5,
        status="failed",
        confidence=0.2,
        drone_pose_local_json=target.scan_pose_local_json,
        scanned_at=datetime.now(UTC),
    )

    observed = observed_target_point(target, result)
    rescan = rescan_waypoints_for_result(target, result)

    assert observed is not None
    assert observed["x_m"] == pytest.approx(11.2)
    assert len(rescan) > 0
    assert all(waypoint.metadata.get("rescan") is True for waypoint in rescan)


@pytest.mark.asyncio
async def test_inspection_relocalizes_before_execution() -> None:
    from backend.modules.warehouse.service.inspection import _relocalize_before_inspection

    class Slam:
        called = False

        async def relocalize(self, timeout_s: float) -> bool:
            self.called = timeout_s == pytest.approx(12.0)
            return True

    navigator = type("Navigator", (), {"slam_provider": Slam()})()

    await _relocalize_before_inspection(navigator, timeout_s=12.0)

    assert navigator.slam_provider.called is True

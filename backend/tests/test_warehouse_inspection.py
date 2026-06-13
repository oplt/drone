from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.modules.missions.flight_profile import flight_profile_for_mission_type
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.schemas import WarehouseLocalPoint, WarehouseScanTargetCreate
from backend.modules.warehouse.service.inspection import (
    MockWarehouseScanner,
    build_inspection_waypoints,
    compute_scan_pose,
    order_targets,
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


@pytest.mark.asyncio
async def test_mock_scanner_returns_expected_barcode() -> None:
    result = await MockWarehouseScanner().scan_target(_target(4, x_m=0.0), timeout_s=8.0)

    assert result.status == "success"
    assert result.detected_barcode == "CODE-4"

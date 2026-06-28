import math

import pytest

from backend.infrastructure.vehicle.frame_conversion import (
    enu_to_local_ned,
    local_ned_position_to_enu,
    local_ned_to_enu,
    warehouse_map_to_odom_enu,
)
from backend.modules.vehicle_runtime.types import EnuCoordinate


def test_known_enu_landmark_converts_to_ned_once() -> None:
    ned = enu_to_local_ned(
        EnuCoordinate(x_m=2.0, y_m=5.0, z_m=3.0, yaw_rad=0.0, frame_id="odom")
    )

    assert (ned.north_m, ned.east_m, ned.down_m) == (5.0, 2.0, -3.0)
    assert ned.yaw_rad == pytest.approx(math.pi / 2)
    telemetry_enu = local_ned_position_to_enu(north_m=5, east_m=2, down_m=-3)
    assert (telemetry_enu.x_m, telemetry_enu.y_m, telemetry_enu.z_m) == (2, 5, 3)


@pytest.mark.parametrize("yaw_rad", [-math.pi, -math.pi / 2, 0.0, math.pi / 2, math.pi])
def test_enu_ned_round_trip_preserves_pose(yaw_rad: float) -> None:
    source = EnuCoordinate(x_m=-4.0, y_m=7.5, z_m=1.25, yaw_rad=yaw_rad)
    restored = local_ned_to_enu(enu_to_local_ned(source))

    assert (restored.x_m, restored.y_m, restored.z_m) == pytest.approx(
        (source.x_m, source.y_m, source.z_m)
    )
    assert math.sin(restored.yaw_rad or 0.0) == pytest.approx(math.sin(yaw_rad))
    assert math.cos(restored.yaw_rad or 0.0) == pytest.approx(math.cos(yaw_rad))


def test_locked_map_transform_is_applied_before_ned_conversion() -> None:
    warehouse_pose = EnuCoordinate(
        x_m=10.0,
        y_m=21.0,
        z_m=2.0,
        yaw_rad=math.pi / 2,
        frame_id="warehouse_map",
    )
    odom_pose = warehouse_map_to_odom_enu(
        warehouse_pose,
        {
            "translation": {"x": 10.0, "y": 20.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 2**-0.5, "w": 2**-0.5},
        },
    )
    ned = enu_to_local_ned(odom_pose)

    assert (odom_pose.x_m, odom_pose.y_m, odom_pose.z_m) == pytest.approx((1.0, 0.0, 2.0))
    assert (ned.north_m, ned.east_m, ned.down_m) == pytest.approx((0.0, 1.0, -2.0))
    assert ned.yaw_rad == pytest.approx(math.pi / 2)


def test_mavlink_boundary_rejects_wrong_frame_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="odom"):
        enu_to_local_ned(EnuCoordinate(0, 0, 0, frame_id="warehouse_map"))
    with pytest.raises(ValueError, match="finite"):
        enu_to_local_ned(EnuCoordinate(float("nan"), 0, 0))

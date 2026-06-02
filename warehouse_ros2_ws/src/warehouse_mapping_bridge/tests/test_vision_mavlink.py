from __future__ import annotations

import math
from types import SimpleNamespace

from warehouse_mapping_bridge.vision_mavlink import (
    enu_quaternion_to_ned_euler_rad,
    odometry_to_vision_pose,
)


def _quat_from_yaw(yaw_rad: float) -> tuple[float, float, float, float]:
    return 0.0, 0.0, math.sin(yaw_rad / 2.0), math.cos(yaw_rad / 2.0)


def _odom(x: float, y: float, z: float, quat: tuple[float, float, float, float]) -> object:
    qx, qy, qz, qw = quat
    return SimpleNamespace(
        pose=SimpleNamespace(
            pose=SimpleNamespace(
                position=SimpleNamespace(x=x, y=y, z=z),
                orientation=SimpleNamespace(x=qx, y=qy, z=qz, w=qw),
            )
        )
    )


def test_enu_identity_orientation_maps_to_ned_east_facing_yaw() -> None:
    roll, pitch, yaw = enu_quaternion_to_ned_euler_rad(0.0, 0.0, 0.0, 1.0)

    assert roll == 0.0
    assert pitch == -0.0
    assert math.isclose(yaw, math.pi / 2.0)


def test_enu_north_facing_yaw_maps_to_zero_ned_yaw() -> None:
    roll, pitch, yaw = enu_quaternion_to_ned_euler_rad(*_quat_from_yaw(math.pi / 2.0))

    assert math.isclose(roll, 0.0, abs_tol=1e-9)
    assert math.isclose(pitch, 0.0, abs_tol=1e-9)
    assert math.isclose(yaw, 0.0, abs_tol=1e-9)


def test_odometry_position_maps_enu_to_ned() -> None:
    estimate = odometry_to_vision_pose(
        _odom(x=3.0, y=4.0, z=2.0, quat=(0.0, 0.0, 0.0, 1.0)),
        now_usec=123,
    )

    assert estimate.usec == 123
    assert estimate.x_north_m == 4.0
    assert estimate.y_east_m == 3.0
    assert estimate.z_down_m == -2.0

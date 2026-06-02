from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class VisionPoseEstimate:
    usec: int
    x_north_m: float
    y_east_m: float
    z_down_m: float
    roll_rad: float
    pitch_rad: float
    yaw_rad: float
    covariance: list[float]
    reset_counter: int = 0


def quaternion_to_euler_rad(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return roll, pitch, yaw


def _quaternion_to_matrix(x: float, y: float, z: float, w: float) -> list[list[float]]:
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm == 0.0:
        x, y, z, w = 0.0, 0.0, 0.0, 1.0
    else:
        x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ]


def _matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [
            sum(a[row][col2] * b[col2][col] for col2 in range(3))
            for col in range(3)
        ]
        for row in range(3)
    ]


def _matrix_to_euler_zyx(matrix: list[list[float]]) -> tuple[float, float, float]:
    # Matrix maps body FRD vectors into world NED. Extract aerospace roll/pitch/yaw.
    pitch = math.asin(max(-1.0, min(1.0, -matrix[2][0])))
    if abs(math.cos(pitch)) > 1e-9:
        roll = math.atan2(matrix[2][1], matrix[2][2])
        yaw = math.atan2(matrix[1][0], matrix[0][0])
    else:
        roll = 0.0
        yaw = math.atan2(-matrix[0][1], matrix[1][1])
    yaw = (yaw + math.pi) % (2.0 * math.pi) - math.pi
    return roll, pitch, yaw


def enu_quaternion_to_ned_euler_rad(
    x: float,
    y: float,
    z: float,
    w: float,
) -> tuple[float, float, float]:
    """Convert ROS ENU FLU body orientation to MAVLink local NED FRD Euler angles."""
    enu_from_flu = _quaternion_to_matrix(x, y, z, w)
    ned_from_enu = [
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
    ]
    flu_from_frd = [
        [1.0, 0.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, -1.0],
    ]
    ned_from_frd = _matmul(_matmul(ned_from_enu, enu_from_flu), flu_from_frd)
    return _matrix_to_euler_zyx(ned_from_frd)


def covariance21(position_var_m2: float, angle_var_rad2: float) -> list[float]:
    cov = [0.0] * 21
    cov[0] = position_var_m2
    cov[6] = position_var_m2
    cov[11] = position_var_m2
    cov[15] = angle_var_rad2
    cov[18] = angle_var_rad2
    cov[20] = angle_var_rad2
    return cov


def odometry_to_vision_pose(message: object, *, now_usec: int | None = None) -> VisionPoseEstimate:
    pose = message.pose.pose
    position = pose.position
    orientation = pose.orientation
    roll, pitch, yaw = enu_quaternion_to_ned_euler_rad(
        float(orientation.x),
        float(orientation.y),
        float(orientation.z),
        float(orientation.w),
    )
    return VisionPoseEstimate(
        usec=now_usec if now_usec is not None else int(time.time() * 1_000_000),
        x_north_m=float(position.y),
        y_east_m=float(position.x),
        z_down_m=-float(position.z),
        roll_rad=roll,
        pitch_rad=pitch,
        yaw_rad=yaw,
        covariance=covariance21(0.05, 0.01),
    )

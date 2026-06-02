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


def enu_quaternion_to_ned_euler_rad(
    x: float,
    y: float,
    z: float,
    w: float,
) -> tuple[float, float, float]:
    """Convert ROS ENU FLU body orientation to MAVLink local NED FRD Euler angles."""
    roll_enu, pitch_enu, yaw_enu = quaternion_to_euler_rad(x, y, z, w)
    roll_ned = roll_enu
    pitch_ned = -pitch_enu
    yaw_ned = math.pi / 2.0 - yaw_enu
    yaw_ned = (yaw_ned + math.pi) % (2.0 * math.pi) - math.pi
    return roll_ned, pitch_ned, yaw_ned


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

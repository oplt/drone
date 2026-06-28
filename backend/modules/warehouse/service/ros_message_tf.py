from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

POINTCLOUD_TF_MAX_AGE_MS = 2000.0
POINTCLOUD_TF_LOOKUP_TIMEOUT_S = 0.15

TfLookupMode = Literal["none", "message_stamp", "latest"]

GAZEBO_POINTCLOUD_FRAME_ALIASES = {
    "iris_rplidar_rgbd/mid360_lidar_link/mid360_lidar": "lidar_link",
    "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera": "rgbd_link",
}


@dataclass(frozen=True)
class MessageTfLookup:
    transform: Any | None
    lookup_mode: TfLookupMode
    source_frame: str
    message_stamp: str | None
    message_age_ms: float | None
    transform_age_ms: float | None

    @property
    def needs_transform(self) -> bool:
        return self.lookup_mode != "none"


def rotation_matrix_from_quaternion_xyzw(
    x: float,
    y: float,
    z: float,
    w: float,
) -> np.ndarray:
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 1e-12:
        return np.eye(3, dtype=np.float32)
    x /= norm
    y /= norm
    z /= norm
    w /= norm
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return np.asarray(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float32,
    )


def stamp_string_from_msg(msg: Any) -> str | None:
    header = getattr(msg, "header", None)
    stamp = getattr(header, "stamp", None) if header is not None else None
    if stamp is None:
        return None
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    return f"{int(sec)}.{int(nanosec):09d}"


def stamp_age_ms(stamp: Any, *, now_ns: int) -> float | None:
    if stamp is None:
        return None
    try:
        stamp_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
    except (AttributeError, TypeError, ValueError):
        return None
    if stamp_ns <= 0 or now_ns < stamp_ns:
        return None
    return round((now_ns - stamp_ns) / 1_000_000.0, 3)


def transform_xyz_points(xyz: np.ndarray, transform: Any | None) -> np.ndarray:
    xyz = np.ascontiguousarray(xyz, dtype=np.float32)
    if transform is None:
        return xyz
    t = transform.transform.translation
    q = transform.transform.rotation
    rotation = rotation_matrix_from_quaternion_xyzw(
        float(q.x),
        float(q.y),
        float(q.z),
        float(q.w),
    )
    translation = np.asarray([float(t.x), float(t.y), float(t.z)], dtype=np.float32)
    return np.ascontiguousarray((xyz @ rotation.T) + translation, dtype=np.float32)


def canonical_pointcloud_source_frame(frame_id: str | None) -> str:
    cleaned = str(frame_id or "").strip().lstrip("/")
    return GAZEBO_POINTCLOUD_FRAME_ALIASES.get(cleaned, cleaned)


def lookup_transform_at_message_stamp(
    tf_buffer: Any,
    *,
    target_frame: str,
    msg: Any,
    source_frame: str | None = None,
    timeout_s: float = POINTCLOUD_TF_LOOKUP_TIMEOUT_S,
) -> Any | None:
    from rclpy.clock import ClockType
    from rclpy.duration import Duration
    from rclpy.time import Time

    header = getattr(msg, "header", None)
    source_frame = canonical_pointcloud_source_frame(
        source_frame if source_frame is not None else getattr(header, "frame_id", None)
    )
    if not source_frame or source_frame == target_frame:
        return None
    stamp = getattr(header, "stamp", None)
    if stamp is None:
        return None
    try:
        stamp_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        lookup_time = Time(nanoseconds=stamp_ns, clock_type=ClockType.ROS_TIME)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
    try:
        return tf_buffer.lookup_transform(
            target_frame,
            source_frame,
            lookup_time,
            timeout=Duration(seconds=float(timeout_s)),
        )
    except Exception:
        return None


def lookup_transform_latest(
    tf_buffer: Any,
    *,
    target_frame: str,
    source_frame: str,
    timeout_s: float = POINTCLOUD_TF_LOOKUP_TIMEOUT_S,
) -> Any | None:
    from rclpy.duration import Duration
    from rclpy.time import Time

    if not source_frame or source_frame == target_frame:
        return None
    try:
        return tf_buffer.lookup_transform(
            target_frame,
            source_frame,
            Time(),
            timeout=Duration(seconds=float(timeout_s)),
        )
    except Exception:
        return None


def resolve_pointcloud_transform(
    tf_buffer: Any,
    *,
    msg: Any,
    global_frame: str,
    now_ns: int,
    max_transform_age_ms: float = POINTCLOUD_TF_MAX_AGE_MS,
) -> MessageTfLookup | None:
    """Resolve TF for a point cloud at the message timestamp.

    Returns None when a transform is required but unavailable or too stale.
    """
    header = getattr(msg, "header", None)
    source_frame = canonical_pointcloud_source_frame(getattr(header, "frame_id", None))
    message_stamp = getattr(header, "stamp", None) if header is not None else None
    message_age_ms = stamp_age_ms(message_stamp, now_ns=now_ns)
    stamp_text = stamp_string_from_msg(msg)

    if not source_frame:
        return None
    if source_frame == global_frame:
        return MessageTfLookup(
            transform=None,
            lookup_mode="none",
            source_frame=source_frame,
            message_stamp=stamp_text,
            message_age_ms=message_age_ms,
            transform_age_ms=None,
        )

    transform = lookup_transform_at_message_stamp(
        tf_buffer,
        target_frame=global_frame,
        msg=msg,
        source_frame=source_frame,
    )
    lookup_mode: TfLookupMode = "message_stamp"
    if transform is None:
        transform = lookup_transform_latest(
            tf_buffer,
            target_frame=global_frame,
            source_frame=source_frame,
        )
        lookup_mode = "latest"
    if transform is None:
        return None

    transform_stamp = getattr(getattr(transform, "header", None), "stamp", None)
    transform_age_ms = stamp_age_ms(transform_stamp, now_ns=now_ns)
    if lookup_mode == "message_stamp":
        freshness_ms = message_age_ms if message_age_ms is not None else transform_age_ms
    else:
        freshness_ms = transform_age_ms if transform_age_ms is not None else message_age_ms
    if freshness_ms is None or freshness_ms > float(max_transform_age_ms):
        return None

    return MessageTfLookup(
        transform=transform,
        lookup_mode=lookup_mode,
        source_frame=source_frame,
        message_stamp=stamp_text,
        message_age_ms=message_age_ms,
        transform_age_ms=transform_age_ms,
    )

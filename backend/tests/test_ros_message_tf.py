from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np

from backend.modules.warehouse.service.ros_message_tf import (
    canonical_pointcloud_source_frame,
    lookup_transform_at_message_stamp,
    resolve_pointcloud_transform,
    rotation_matrix_from_quaternion_xyzw,
    stamp_age_ms,
    transform_xyz_points,
)


def test_gazebo_sensor_frames_map_to_canonical_tf_frames() -> None:
    assert (
        canonical_pointcloud_source_frame(
            "iris_rplidar_rgbd/mid360_lidar_link/mid360_lidar"
        )
        == "lidar_link"
    )
    assert (
        canonical_pointcloud_source_frame(
            "iris_rplidar_rgbd/front_rgbd_camera_link/front_rgbd_camera"
        )
        == "rgbd_link"
    )


def test_transform_xyz_points_applies_translation() -> None:
    transform = SimpleNamespace(
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=10.0, y=20.0, z=1.0),
            rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        )
    )
    xyz = np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32)
    transformed = transform_xyz_points(xyz, transform)
    assert np.allclose(transformed[0], [11.0, 22.0, 4.0], atol=1e-5)


def test_stamp_age_ms_returns_elapsed_time() -> None:
    stamp = SimpleNamespace(sec=10, nanosec=250_000_000)
    assert stamp_age_ms(stamp, now_ns=12_500_000_000) == 2250.0


def test_lookup_transform_at_message_stamp_uses_message_time() -> None:
    class _Buffer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, object]] = []

        def lookup_transform(self, target: str, source: str, stamp: object, timeout: object) -> object:
            self.calls.append((target, source, stamp))
            return SimpleNamespace(
                header=SimpleNamespace(stamp=SimpleNamespace(sec=5, nanosec=0)),
                transform=SimpleNamespace(
                    translation=SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
                ),
            )

    msg = SimpleNamespace(
        header=SimpleNamespace(
            frame_id="camera_optical_frame",
            stamp=SimpleNamespace(sec=5, nanosec=0),
        )
    )
    buffer = _Buffer()
    transform = lookup_transform_at_message_stamp(
        buffer,
        target_frame="odom",
        msg=msg,
    )
    assert transform is not None
    assert buffer.calls[0][:2] == ("odom", "camera_optical_frame")


def test_resolve_pointcloud_transform_rejects_stale_tf() -> None:
    class _Buffer:
        def lookup_transform(self, target: str, source: str, stamp: object, timeout: object) -> object:
            return SimpleNamespace(
                header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)),
                transform=SimpleNamespace(
                    translation=SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
                ),
            )

    msg = SimpleNamespace(
        header=SimpleNamespace(
            frame_id="lidar_link",
            stamp=SimpleNamespace(sec=10, nanosec=0),
        )
    )
    now_ns = 13_000_000_000
    assert resolve_pointcloud_transform(_Buffer(), msg=msg, global_frame="odom", now_ns=now_ns) is None


def test_resolve_pointcloud_transform_accepts_historical_transform_stamp() -> None:
    class _Buffer:
        def lookup_transform(self, target: str, source: str, stamp: object, timeout: object) -> object:
            return SimpleNamespace(
                header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)),
                transform=SimpleNamespace(
                    translation=SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
                ),
            )

    msg = SimpleNamespace(
        header=SimpleNamespace(
            frame_id="lidar_link",
            stamp=SimpleNamespace(sec=10, nanosec=0),
        )
    )
    now_ns = 10_400_000_000
    resolved = resolve_pointcloud_transform(_Buffer(), msg=msg, global_frame="odom", now_ns=now_ns)
    assert resolved is not None
    assert resolved.lookup_mode == "message_stamp"
    assert resolved.message_age_ms == 400.0


def test_resolve_pointcloud_transform_accepts_fresh_message_stamp_tf() -> None:
    class _Buffer:
        def lookup_transform(self, target: str, source: str, stamp: object, timeout: object) -> object:
            return SimpleNamespace(
                header=SimpleNamespace(stamp=SimpleNamespace(sec=10, nanosec=100_000_000)),
                transform=SimpleNamespace(
                    translation=SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
                ),
            )

    msg = SimpleNamespace(
        header=SimpleNamespace(
            frame_id="lidar_link",
            stamp=SimpleNamespace(sec=10, nanosec=0),
        )
    )
    now_ns = 10_200_000_000
    resolved = resolve_pointcloud_transform(_Buffer(), msg=msg, global_frame="odom", now_ns=now_ns)
    assert resolved is not None
    assert resolved.lookup_mode == "message_stamp"
    assert resolved.transform_age_ms == 100.0


def test_rotation_matrix_identity_for_unit_quaternion() -> None:
    matrix = rotation_matrix_from_quaternion_xyzw(0.0, 0.0, 0.0, 1.0)
    assert np.allclose(matrix, np.eye(3), atol=1e-6)

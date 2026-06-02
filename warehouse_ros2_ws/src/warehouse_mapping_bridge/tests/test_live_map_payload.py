from __future__ import annotations

import struct
from types import SimpleNamespace

from warehouse_mapping_bridge.live_map_publisher_node import bbox_from_points, pointcloud_xyz_sample


def _field(name: str, offset: int) -> object:
    return SimpleNamespace(name=name, offset=offset)


def test_pointcloud_xyz_sample_extracts_downsampled_points() -> None:
    points = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)]
    data = b"".join(struct.pack("<fff", *point) for point in points)
    message = SimpleNamespace(
        width=3,
        height=1,
        point_step=12,
        is_bigendian=False,
        fields=[_field("x", 0), _field("y", 4), _field("z", 8)],
        data=data,
    )

    assert pointcloud_xyz_sample(message, max_points=2) == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


def test_bbox_from_points_uses_real_sample_extents() -> None:
    bbox = bbox_from_points(
        [[1.0, 2.0, 3.0], [-1.0, 4.0, 0.5]],
        {"x_m": 0.0, "y_m": 0.0, "z_m": 0.0, "frame_id": "map"},
    )

    assert bbox == [-1.0, 2.0, 0.5, 1.0, 4.0, 3.0]

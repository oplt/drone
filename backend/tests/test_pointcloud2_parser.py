from __future__ import annotations

import struct

import numpy as np

from backend.modules.warehouse.service.pointcloud2_parser import (
    encode_xyz32,
    encode_xyzrgb32,
    parse_pointcloud2_yaml,
)


def _build_yaml_payload(*, with_rgb: bool = True) -> dict:
    point_step = 16 if with_rgb else 12
    fields = [
        {"name": "x", "offset": 0, "datatype": 7, "count": 1},
        {"name": "y", "offset": 4, "datatype": 7, "count": 1},
        {"name": "z", "offset": 8, "datatype": 7, "count": 1},
    ]
    if with_rgb:
        fields.append({"name": "rgb", "offset": 12, "datatype": 7, "count": 1})

    rows: list[int] = []
    values = [
        (1.0, 2.0, 3.0, struct.unpack("f", struct.pack("I", 0x00FF8040))[0]),
        (float("nan"), 0.0, 0.0, 0.0),
        (4.0, 5.0, 6.0, struct.unpack("f", struct.pack("I", 0x0000FF00))[0]),
    ]

    for x, y, z, rgb in values:
        row = bytearray(point_step)
        struct.pack_into("<f", row, 0, x)
        struct.pack_into("<f", row, 4, y)
        struct.pack_into("<f", row, 8, z)
        if with_rgb:
            struct.pack_into("<f", row, 12, rgb)
        rows.extend(row)

    return {
        "header": {"frame_id": "camera_link"},
        "fields": fields,
        "point_step": point_step,
        "is_bigendian": False,
        "data": rows,
    }


def test_parse_pointcloud2_yaml_skips_nan_and_keeps_rgb() -> None:
    payload = _build_yaml_payload(with_rgb=True)
    parsed = parse_pointcloud2_yaml(payload, max_points=10, downsample=False)

    assert parsed is not None
    assert parsed.point_count == 2
    assert parsed.has_rgb is True
    assert parsed.xyz.shape == (2, 3)
    assert parsed.rgb is not None
    assert parsed.rgb.shape == (2, 3)


def test_parse_pointcloud2_yaml_height_fallback_without_rgb() -> None:
    payload = _build_yaml_payload(with_rgb=False)
    parsed = parse_pointcloud2_yaml(payload, max_points=10, downsample=False)

    assert parsed is not None
    assert parsed.has_rgb is False
    assert parsed.rgb is not None
    assert parsed.rgb.shape[0] == parsed.point_count


def test_binary_encoders_roundtrip_shape() -> None:
    xyz = np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
    rgb = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)

    xyz_bytes = encode_xyz32(xyz)
    assert len(xyz_bytes) == xyz.size * 4

    rgb_bytes = encode_xyzrgb32(xyz, rgb)
    assert len(rgb_bytes) == xyz.size * 4 + rgb.size

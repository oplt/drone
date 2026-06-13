from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from backend.modules.warehouse.service.nvblox_mesh_adapter import (
    build_glb_from_mesh_arrays,
    mesh_topic_supported,
    parse_nvblox_mesh_message,
)
from backend.modules.warehouse.service.nvblox_voxel_layer_parser import (
    parse_voxel_block_layer_msg,
)


def test_mesh_topic_supported() -> None:
    assert mesh_topic_supported() is True


def test_parse_voxel_block_layer_centers_and_colors() -> None:
    msg = SimpleNamespace(
        clear=False,
        blocks=[
            SimpleNamespace(
                centers=[
                    SimpleNamespace(x=1.0, y=2.0, z=3.0),
                    SimpleNamespace(x=4.0, y=5.0, z=6.0),
                ],
                colors=[
                    SimpleNamespace(r=1.0, g=0.0, b=0.0),
                    SimpleNamespace(r=0.0, g=1.0, b=0.0),
                ],
            )
        ],
    )
    parsed = parse_voxel_block_layer_msg(msg, max_points=10)
    assert parsed is not None
    assert parsed.point_count == 2
    assert parsed.has_rgb is True
    assert parsed.xyz.shape == (2, 3)
    assert parsed.rgb is not None
    assert float(parsed.rgb[0, 0]) == 1.0


def test_parse_voxel_block_layer_clear_returns_none() -> None:
    msg = SimpleNamespace(clear=True, blocks=[])
    assert parse_voxel_block_layer_msg(msg) is None


def test_build_glb_from_mesh_arrays_produces_glb_header() -> None:
    positions = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    indices = np.array([[0, 1, 2]], dtype=np.uint32)
    colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    glb = build_glb_from_mesh_arrays(positions=positions, indices=indices, colors=colors)
    assert glb[:4] == b"glTF"
    assert len(glb) > 64


def test_parse_nvblox_mesh_message_builds_glb() -> None:
    msg = SimpleNamespace(
        clear=False,
        blocks=[
            SimpleNamespace(
                vertices=[
                    SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    SimpleNamespace(x=1.0, y=0.0, z=0.0),
                    SimpleNamespace(x=0.0, y=1.0, z=0.0),
                ],
                colors=[
                    SimpleNamespace(r=0.9, g=0.1, b=0.1),
                    SimpleNamespace(r=0.1, g=0.9, b=0.1),
                    SimpleNamespace(r=0.1, g=0.1, b=0.9),
                ],
                triangles=[0, 1, 2],
            )
        ],
    )
    glb = parse_nvblox_mesh_message(msg)
    assert glb is not None
    assert glb[:4] == b"glTF"

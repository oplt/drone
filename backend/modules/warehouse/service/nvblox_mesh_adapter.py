from __future__ import annotations

import json
import struct
from typing import Any

import numpy as np


def mesh_topic_supported() -> bool:
    return True


def _align4(n: int) -> int:
    return (n + 3) & ~3


def build_glb_from_mesh_arrays(
    *,
    positions: np.ndarray,
    indices: np.ndarray,
    colors: np.ndarray | None = None,
) -> bytes:
    """Build a minimal GLB 2.0 buffer with one colored triangle mesh."""
    if positions.size == 0 or indices.size == 0:
        raise ValueError("Mesh arrays are empty")

    pos = np.ascontiguousarray(positions, dtype=np.float32).reshape((-1, 3))
    tri = np.ascontiguousarray(indices, dtype=np.uint32).reshape((-1, 3))
    color = None
    if colors is not None and colors.shape[0] == pos.shape[0]:
        color = np.clip(np.asarray(colors, dtype=np.float32).reshape((-1, 3)), 0.0, 1.0)
        color_u8 = np.ascontiguousarray((color * 255.0).astype(np.uint8))
    else:
        color_u8 = None

    bin_parts: list[bytes] = []
    buffer_views: list[dict[str, int]] = []
    accessors: list[dict[str, int | float | str]] = []
    byte_offset = 0

    def _append_array(data: bytes, *, target: str, component_type: int, count: int, type_str: str):
        nonlocal byte_offset
        if byte_offset % 4 != 0:
            pad = 4 - (byte_offset % 4)
            bin_parts.append(b"\x00" * pad)
            byte_offset += pad
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": byte_offset,
                "byteLength": len(data),
                "target": target,
            }
        )
        accessors.append(
            {
                "bufferView": len(buffer_views) - 1,
                "componentType": component_type,
                "count": count,
                "type": type_str,
            }
        )
        bin_parts.append(data)
        byte_offset += len(data)

    _append_array(
        pos.tobytes(),
        target=34962,
        component_type=5126,
        count=pos.shape[0],
        type_str="VEC3",
    )
    pos_min = pos.min(axis=0).tolist()
    pos_max = pos.max(axis=0).tolist()
    accessors[-1]["min"] = pos_min
    accessors[-1]["max"] = pos_max

    color_accessor_index: int | None = None
    if color_u8 is not None:
        color_accessor_index = len(accessors)
        _append_array(
            color_u8.tobytes(),
            target=34962,
            component_type=5121,
            count=color_u8.shape[0],
            type_str="VEC3",
        )
        accessors[-1]["normalized"] = True

    _append_array(
        tri.tobytes(),
        target=34963,
        component_type=5125,
        count=tri.size,
        type_str="SCALAR",
    )
    index_accessor = len(accessors) - 1

    attributes: dict[str, int] = {"POSITION": 0}
    if color_accessor_index is not None:
        attributes["COLOR_0"] = color_accessor_index

    gltf = {
        "asset": {"version": "2.0", "generator": "drone_app_nvblox_mesh_adapter"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": attributes,
                        "indices": index_accessor,
                        "mode": 4,
                    }
                ]
            }
        ],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": byte_offset}],
    }

    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_padded = json_chunk + b" " * (_align4(len(json_chunk)) - len(json_chunk))
    bin_blob = b"".join(bin_parts)
    if len(bin_blob) % 4 != 0:
        bin_blob += b"\x00" * (4 - (len(bin_blob) % 4))

    total_length = 12 + 8 + len(json_padded) + 8 + len(bin_blob)
    header = struct.pack("<4sII", b"glTF", 2, total_length)
    json_header = struct.pack("<I4s", len(json_padded), b"JSON") + json_padded
    bin_header = struct.pack("<I4s", len(bin_blob), b"BIN\x00") + bin_blob
    return header + json_header + bin_header


def parse_nvblox_mesh_message(
    msg: Any,
    *,
    max_vertices: int = 120_000,
) -> bytes | None:
    """Convert nvblox_msgs/Mesh into GLB bytes for live-map storage."""
    if bool(getattr(msg, "clear", False)):
        return None

    blocks = getattr(msg, "blocks", None) or []
    if not blocks:
        return None

    positions: list[list[float]] = []
    colors: list[list[float]] = []
    indices: list[int] = []
    base = 0

    for block in blocks:
        vertices = getattr(block, "vertices", None) or []
        triangles = getattr(block, "triangles", None) or []
        block_colors = getattr(block, "colors", None) or []
        if not vertices or not triangles:
            continue

        for vertex in vertices:
            positions.append(
                [
                    float(getattr(vertex, "x", 0.0)),
                    float(getattr(vertex, "y", 0.0)),
                    float(getattr(vertex, "z", 0.0)),
                ]
            )
        for color_index, color in enumerate(block_colors):
            if color_index >= len(positions) - base:
                break
            colors.append(
                [
                    float(getattr(color, "r", 0.8)),
                    float(getattr(color, "g", 0.8)),
                    float(getattr(color, "b", 0.8)),
                ]
            )
        for triangle_index in triangles:
            indices.append(base + int(triangle_index))
        base += len(vertices)

    if not positions or not indices:
        return None

    pos = np.asarray(positions, dtype=np.float32)
    tri = np.asarray(indices, dtype=np.uint32)
    if tri.size % 3 != 0:
        tri = tri[: tri.size - (tri.size % 3)]
    if tri.size == 0:
        return None
    tri = tri.reshape((-1, 3))

    color_array: np.ndarray | None = None
    if len(colors) == pos.shape[0]:
        color_array = np.asarray(colors, dtype=np.float32)

    if pos.shape[0] > max_vertices:
        stride = max(1, int(np.ceil(pos.shape[0] / max_vertices)))
        keep = np.arange(0, pos.shape[0], stride, dtype=np.int64)
        remap = -np.ones(pos.shape[0], dtype=np.int64)
        remap[keep] = np.arange(keep.shape[0], dtype=np.int64)
        pos = pos[keep]
        if color_array is not None:
            color_array = color_array[keep]
        remapped_faces = []
        for face in tri:
            mapped = [int(remap[int(index)]) for index in face]
            if any(index < 0 for index in mapped):
                continue
            remapped_faces.append(mapped)
        if not remapped_faces:
            return None
        tri = np.asarray(remapped_faces, dtype=np.uint32)

    return build_glb_from_mesh_arrays(positions=pos, indices=tri, colors=color_array)

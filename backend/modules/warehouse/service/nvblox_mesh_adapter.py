from __future__ import annotations

import json
import struct
from typing import Any

import numpy as np


def mesh_topic_supported() -> bool:
    return True


def _align4(n: int) -> int:
    return (int(n) + 3) & ~3


def _as_positions(positions: np.ndarray) -> np.ndarray:
    pos = np.ascontiguousarray(positions, dtype=np.float32).reshape((-1, 3))
    finite = np.isfinite(pos).all(axis=1)
    if not bool(finite.all()):
        pos = pos[finite]
    if pos.size == 0:
        raise ValueError("Mesh positions are empty or non-finite")
    return np.ascontiguousarray(pos, dtype=np.float32)


def build_glb_from_mesh_arrays(
    *,
    positions: np.ndarray,
    indices: np.ndarray,
    colors: np.ndarray | None = None,
) -> bytes:
    """Build a minimal GLB 2.0 buffer with one optional colored triangle mesh."""
    if positions.size == 0 or indices.size == 0:
        raise ValueError("Mesh arrays are empty")

    pos = _as_positions(positions)
    tri = np.ascontiguousarray(indices, dtype=np.uint32).reshape((-1, 3))
    if tri.size == 0:
        raise ValueError("Mesh triangle indices are empty")
    if int(tri.max(initial=0)) >= pos.shape[0]:
        valid = (tri < pos.shape[0]).all(axis=1)
        tri = tri[valid]
        if tri.size == 0:
            raise ValueError("Mesh triangle indices reference no valid vertices")

    color_u8 = None
    if colors is not None and colors.shape[0] == pos.shape[0]:
        color = np.asarray(colors, dtype=np.float32).reshape((-1, 3))
        if np.nanmax(color) > 1.0:
            color = color / 255.0
        color = np.nan_to_num(color, nan=0.8, posinf=1.0, neginf=0.0)
        color_u8 = np.ascontiguousarray((np.clip(color, 0.0, 1.0) * 255.0).astype(np.uint8))

    bin_parts: list[bytes] = []
    buffer_views: list[dict[str, int]] = []
    accessors: list[dict[str, Any]] = []
    byte_offset = 0

    def _append_array(data: bytes, *, target: int, component_type: int, count: int, type_str: str) -> int:
        nonlocal byte_offset
        if byte_offset % 4 != 0:
            pad = 4 - (byte_offset % 4)
            bin_parts.append(b"\x00" * pad)
            byte_offset += pad
        buffer_views.append({"buffer": 0, "byteOffset": byte_offset, "byteLength": len(data), "target": target})
        accessors.append({"bufferView": len(buffer_views) - 1, "componentType": component_type, "count": count, "type": type_str})
        bin_parts.append(data)
        byte_offset += len(data)
        return len(accessors) - 1

    position_accessor = _append_array(pos.tobytes(), target=34962, component_type=5126, count=pos.shape[0], type_str="VEC3")
    accessors[position_accessor]["min"] = pos.min(axis=0).astype(float).tolist()
    accessors[position_accessor]["max"] = pos.max(axis=0).astype(float).tolist()

    color_accessor_index: int | None = None
    if color_u8 is not None:
        color_accessor_index = _append_array(color_u8.tobytes(), target=34962, component_type=5121, count=color_u8.shape[0], type_str="VEC3")
        accessors[color_accessor_index]["normalized"] = True

    index_accessor = _append_array(np.ascontiguousarray(tri, dtype=np.uint32).tobytes(), target=34963, component_type=5125, count=int(tri.size), type_str="SCALAR")

    attributes: dict[str, int] = {"POSITION": position_accessor}
    if color_accessor_index is not None:
        attributes["COLOR_0"] = color_accessor_index

    gltf = {
        "asset": {"version": "2.0", "generator": "drone_app_nvblox_mesh_adapter"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": attributes, "indices": index_accessor, "mode": 4}]}],
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
    return (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<I4s", len(json_padded), b"JSON")
        + json_padded
        + struct.pack("<I4s", len(bin_blob), b"BIN\x00")
        + bin_blob
    )


def _vertex_tuple(vertex: Any) -> tuple[float, float, float] | None:
    try:
        point = (float(getattr(vertex, "x", 0.0)), float(getattr(vertex, "y", 0.0)), float(getattr(vertex, "z", 0.0)))
    except (TypeError, ValueError):
        return None
    if not all(np.isfinite(point)):
        return None
    return point


def _color_tuple(color: Any) -> tuple[float, float, float] | None:
    try:
        rgb = (float(getattr(color, "r", 0.8)), float(getattr(color, "g", 0.8)), float(getattr(color, "b", 0.8)))
    except (TypeError, ValueError):
        return None
    if not all(np.isfinite(rgb)):
        return None
    if max(rgb) > 1.0:
        rgb = tuple(v / 255.0 for v in rgb)
    return tuple(float(np.clip(v, 0.0, 1.0)) for v in rgb)


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

    max_vertices = max(3, int(max_vertices or 3))
    positions: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float] | None] = []
    indices: list[int] = []
    base = 0

    for block in blocks:
        vertices = getattr(block, "vertices", None) or []
        triangles = getattr(block, "triangles", None) or []
        block_colors = getattr(block, "colors", None) or []
        if not vertices or not triangles:
            continue

        local_remap: dict[int, int] = {}
        for local_index, vertex in enumerate(vertices):
            point = _vertex_tuple(vertex)
            if point is None:
                continue
            local_remap[local_index] = base + len(local_remap)
            positions.append(point)
            color = _color_tuple(block_colors[local_index]) if local_index < len(block_colors) else None
            colors.append(color)

        raw = [int(v) for v in triangles]
        if len(raw) % 3:
            raw = raw[: len(raw) - (len(raw) % 3)]
        for i in range(0, len(raw), 3):
            face = raw[i : i + 3]
            if all(index in local_remap for index in face):
                mapped = [local_remap[index] for index in face]
                if len(set(mapped)) == 3:
                    indices.extend(mapped)
        base += len(local_remap)

    if not positions or not indices:
        return None

    pos = np.asarray(positions, dtype=np.float32)
    tri = np.asarray(indices, dtype=np.uint32).reshape((-1, 3))
    color_array: np.ndarray | None = None
    if colors and all(color is not None for color in colors) and len(colors) == pos.shape[0]:
        color_array = np.asarray(colors, dtype=np.float32)

    if pos.shape[0] > max_vertices:
        stride = max(1, int(np.ceil(pos.shape[0] / max_vertices)))
        keep = np.arange(0, pos.shape[0], stride, dtype=np.int64)
        remap = -np.ones(pos.shape[0], dtype=np.int64)
        remap[keep] = np.arange(keep.shape[0], dtype=np.int64)
        pos = pos[keep]
        if color_array is not None:
            color_array = color_array[keep]
        mapped = remap[tri]
        valid = (mapped >= 0).all(axis=1)
        mapped = mapped[valid]
        degenerate = (mapped[:, 0] == mapped[:, 1]) | (mapped[:, 1] == mapped[:, 2]) | (mapped[:, 0] == mapped[:, 2]) if mapped.size else np.asarray([], dtype=bool)
        mapped = mapped[~degenerate]
        if mapped.size == 0:
            return None
        tri = np.ascontiguousarray(mapped, dtype=np.uint32)

    return build_glb_from_mesh_arrays(positions=pos, indices=tri, colors=color_array)

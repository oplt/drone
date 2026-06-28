from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from backend.modules.warehouse.service.frame_contract import CALIBRATED_FRAME_EDGES

REQUIRED_FRAME_EDGES = CALIBRATED_FRAME_EDGES


def normalize_sensor_extrinsics(payload: dict[str, Any]) -> dict[str, Any]:
    transforms = payload.get("transforms") if isinstance(payload, dict) else None
    if not isinstance(transforms, list) or len(transforms) != len(REQUIRED_FRAME_EDGES):
        raise ValueError("extrinsics must define exactly the required stable frame transforms")
    normalized: list[dict[str, Any]] = []
    edges: set[tuple[str, str]] = set()
    children: set[str] = set()
    for item in transforms:
        if not isinstance(item, dict):
            raise ValueError("each extrinsic transform must be an object")
        parent = str(item.get("parent_frame") or "").strip()
        child = str(item.get("child_frame") or "").strip()
        edge = (parent, child)
        if edge not in REQUIRED_FRAME_EDGES or edge in edges or child in children:
            raise ValueError(f"invalid or duplicate sensor frame edge: {parent}->{child}")
        try:
            translation = {axis: float(item["translation"][axis]) for axis in ("x", "y", "z")}
            rotation = {axis: float(item["rotation"][axis]) for axis in ("x", "y", "z", "w")}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "each transform requires translation{x,y,z} and rotation{x,y,z,w}"
            ) from exc
        values = [*translation.values(), *rotation.values()]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("extrinsic transform values must be finite")
        norm = math.sqrt(sum(value * value for value in rotation.values()))
        if abs(norm - 1.0) > 1e-3:
            raise ValueError("extrinsic rotation quaternion must be normalized")
        edges.add(edge)
        children.add(child)
        normalized.append(
            {
                "parent_frame": parent,
                "child_frame": child,
                "translation": translation,
                "rotation": rotation,
            }
        )
    if edges != REQUIRED_FRAME_EDGES:
        raise ValueError("extrinsics frame tree is incomplete")
    normalized.sort(key=lambda item: (item["parent_frame"], item["child_frame"]))
    return {"schema_version": 1, "transforms": normalized}


def sensor_calibration_checksum(payload: dict[str, Any]) -> str:
    normalized = normalize_sensor_extrinsics(payload)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

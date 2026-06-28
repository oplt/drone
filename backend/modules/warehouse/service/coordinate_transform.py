"""Typed, ROS-independent homogeneous coordinate transforms."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Vector3:
    x: float
    y: float
    z: float


def homogeneous_matrix(transform: dict) -> np.ndarray:
    t, q = transform["translation"], transform["rotation"]
    x, y, z, w = (float(q[k]) for k in ("x", "y", "z", "w"))
    if not all(math.isfinite(v) for v in (*t.values(), x, y, z, w)):
        raise ValueError("transform contains non-finite values")
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if not math.isclose(norm, 1.0, abs_tol=1e-6):
        raise ValueError("quaternion must be normalized")
    matrix = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), float(t["x"])],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), float(t["y"])],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), float(t["z"])],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    return matrix


def transform_vectors(
    vectors: list[Vector3], transform: dict, *, inverse: bool = False
) -> list[Vector3]:
    matrix = homogeneous_matrix(transform)
    if inverse:
        matrix = np.linalg.inv(matrix)
    return [Vector3(*(matrix @ np.array([v.x, v.y, v.z, 1.0]))[:3]) for v in vectors]

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def ensure_closed_ring(
    coords: Sequence[T],
    *,
    min_points: int = 3,
    error_message: str = "Polygon needs at least 3 points",
) -> list[T]:
    if len(coords) < min_points:
        raise ValueError(error_message)
    out = list(coords)
    if out[0] != out[-1]:
        out.append(out[0])
    return out

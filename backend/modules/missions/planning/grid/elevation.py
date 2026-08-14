from __future__ import annotations

from typing import Protocol


class ElevationProvider(Protocol):
    """Callable: (lat, lon) → metres above MSL."""

    def __call__(self, lat: float, lon: float) -> float: ...


class BatchElevationProvider(Protocol):
    """Callable: [(lat, lon), ...] → [metres above MSL, ...]."""

    def __call__(self, coords: list[tuple[float, float]]) -> list[float]: ...

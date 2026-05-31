from __future__ import annotations

import math
import time
from typing import Any, Awaitable, Callable

from backend.core.types.geo import haversine_km


class TerrainCache:
    """Small in-memory TTL cache for terrain elevation lookups."""

    def __init__(self, precision: float = 1e-5, ttl_seconds: float | None = 300):
        self.precision = max(float(precision), 1e-9)
        self.ttl = ttl_seconds
        self.decimal_places = max(0, -int(math.floor(math.log10(self.precision))))

        self._cache: dict[str, tuple[float, float]] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, lat: float, lon: float) -> str:
        return (
            f"{round(float(lat), self.decimal_places):.{self.decimal_places}f},"
            f"{round(float(lon), self.decimal_places):.{self.decimal_places}f}"
        )

    def get(self, lat: float, lon: float) -> float | None:
        key = self._make_key(lat, lon)
        item = self._cache.get(key)

        if item is None:
            self._misses += 1
            return None

        elevation, ts = item
        if self.ttl is None or (time.time() - ts) < float(self.ttl):
            self._hits += 1
            return elevation

        self._cache.pop(key, None)
        self._misses += 1
        return None

    def set(self, lat: float, lon: float, elevation: float | None) -> None:
        if elevation is not None:
            self._cache[self._make_key(lat, lon)] = (float(elevation), time.time())

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
        }

    async def get_or_fetch(
            self,
            lat: float,
            lon: float,
            fetcher: Callable[[float, float], Awaitable[float | None]],
    ) -> float | None:
        cached = self.get(lat, lon)
        if cached is not None:
            return cached

        elevation = await fetcher(lat, lon)
        self.set(lat, lon, elevation)
        return elevation


class DistanceCache:
    """Cache for pairwise distances in meters."""

    def __init__(self) -> None:
        self._cache: dict[tuple[float, float, float, float], float] = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(
            lat1: float,
            lon1: float,
            lat2: float,
            lon2: float,
    ) -> tuple[float, float, float, float]:
        a = (round(float(lat1), 6), round(float(lon1), 6))
        b = (round(float(lat2), 6), round(float(lon2), 6))
        p1, p2 = sorted((a, b))
        return p1[0], p1[1], p2[0], p2[1]

    def get(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
        key = self._make_key(lat1, lon1, lat2, lon2)
        value = self._cache.get(key)

        if value is None:
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, lat1: float, lon1: float, lat2: float, lon2: float, distance: float) -> None:
        self._cache[self._make_key(lat1, lon1, lat2, lon2)] = float(distance)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
        }


def fast_local_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))
    d_lat = lat2_rad - lat1_rad
    d_lon = math.radians(float(lon2) - float(lon1))

    x = d_lon * math.cos((lat1_rad + lat2_rad) * 0.5)
    return 6371000.0 * math.hypot(x, d_lat)


def optimized_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        threshold_deg: float = 0.1,
) -> float:
    if abs(float(lat1) - float(lat2)) > threshold_deg or abs(float(lon1) - float(lon2)) > threshold_deg:
        return haversine_km(float(lat1), float(lon1), float(lat2), float(lon2)) * 1000.0

    return fast_local_distance(float(lat1), float(lon1), float(lat2), float(lon2))
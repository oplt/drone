from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
from dataclasses import dataclass, field
from typing import Any

from .cache import DistanceCache, TerrainCache, optimized_distance


def _lat_lon(wp: Any) -> tuple[float, float] | None:
    lat = getattr(wp, "lat", None)
    lon = getattr(wp, "lon", None)

    if lat is None or lon is None:
        return None

    return float(lat), float(lon)


def _xy(wp: Any) -> tuple[float, float] | None:
    x = getattr(wp, "x_m", None)
    y = getattr(wp, "y_m", None)

    if x is None or y is None:
        return None

    return float(x), float(y)


def _segment_distance_m(a: Any, b: Any, cache: DistanceCache | None = None) -> float:
    ll_a = _lat_lon(a)
    ll_b = _lat_lon(b)

    if ll_a and ll_b:
        if cache:
            cached = cache.get(ll_a[0], ll_a[1], ll_b[0], ll_b[1])
            if cached is not None:
                return cached

        distance = optimized_distance(ll_a[0], ll_a[1], ll_b[0], ll_b[1])

        if cache:
            cache.set(ll_a[0], ll_a[1], ll_b[0], ll_b[1], distance)

        return distance

    xy_a = _xy(a)
    xy_b = _xy(b)

    if xy_a and xy_b:
        return math.hypot(xy_b[0] - xy_a[0], xy_b[1] - xy_a[1])

    return 0.0


@dataclass
class PrecomputedMissionData:
    waypoints: list[Any]
    segment_distances: list[float] = field(default_factory=list)
    cumulative_distances: list[float] = field(default_factory=list)
    terrain_elevations: list[float | None] = field(default_factory=list)
    bearings: list[float] = field(default_factory=list)
    total_distance: float = 0.0
    estimated_duration: float = 0.0

    def compute(self, distance_cache: DistanceCache | None = None) -> None:
        self.segment_distances = []
        self.cumulative_distances = [0.0]
        self.bearings = []

        for a, b in zip(self.waypoints, self.waypoints[1:]):
            distance = _segment_distance_m(a, b, distance_cache)
            self.segment_distances.append(distance)
            self.cumulative_distances.append(self.cumulative_distances[-1] + distance)
            self.bearings.append(self._bearing(a, b))

        self.total_distance = self.cumulative_distances[-1] if self.cumulative_distances else 0.0

    @staticmethod
    def _bearing(a: Any, b: Any) -> float:
        ll_a = _lat_lon(a)
        ll_b = _lat_lon(b)

        if ll_a and ll_b:
            lat1 = math.radians(ll_a[0])
            lat2 = math.radians(ll_b[0])
            dlon = math.radians(ll_b[1] - ll_a[1])

            y = math.sin(dlon) * math.cos(lat2)
            x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
            return math.atan2(y, x)

        xy_a = _xy(a)
        xy_b = _xy(b)

        if xy_a and xy_b:
            return math.atan2(xy_b[0] - xy_a[0], xy_b[1] - xy_a[1])

        return 0.0

    def get_segment_distance(self, idx: int) -> float:
        if 0 <= idx < len(self.segment_distances):
            return self.segment_distances[idx]

        raise IndexError(f"Segment index {idx} out of range")

    def get_distance_between(self, start_idx: int, end_idx: int) -> float:
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        n = len(self.cumulative_distances)

        if start_idx < 0 or end_idx < 0 or start_idx >= n or end_idx >= n:
            raise IndexError(
                f"Waypoint index out of range: start={start_idx}, end={end_idx}, count={n}"
            )

        return self.cumulative_distances[end_idx] - self.cumulative_distances[start_idx]

    def get_terrain_at(self, idx: int) -> float | None:
        return self.terrain_elevations[idx] if 0 <= idx < len(self.terrain_elevations) else None


class MissionDataPreprocessor:
    def __init__(self, terrain_cache: TerrainCache | None = None):
        self.terrain_cache = terrain_cache or TerrainCache()
        self.distance_cache = DistanceCache()
        self._precomputed: dict[str, PrecomputedMissionData] = {}

    @staticmethod
    def _cache_key(waypoints: list[Any]) -> str:
        summary = []

        for wp in waypoints:
            ll = _lat_lon(wp)
            xy = _xy(wp)

            summary.append(
                {
                    "lat": round(ll[0], 7) if ll else None,
                    "lon": round(ll[1], 7) if ll else None,
                    "x": round(xy[0], 3) if xy else None,
                    "y": round(xy[1], 3) if xy else None,
                    "alt": round(float(getattr(wp, "alt", getattr(wp, "z_m", 0.0)) or 0.0), 2),
                }
            )

        payload = json.dumps(summary, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    async def _call_maybe_async(fn: Any, *args: Any) -> Any:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args)

        result = await asyncio.to_thread(fn, *args)

        if inspect.isawaitable(result):
            return await result

        return result

    @staticmethod
    def _value_from_batch_result(
            result: Any,
            coord: tuple[float, float],
            offset: int,
    ) -> float | None:
        if isinstance(result, dict):
            return result.get(coord) or result.get(f"{coord[0]},{coord[1]}")

        if isinstance(result, (list, tuple)) and offset < len(result):
            return result[offset]

        return None

    async def preprocess(self, waypoints: list[Any], terrain_data: Any = None) -> PrecomputedMissionData:
        cache_key = self._cache_key(waypoints)
        cached = self._precomputed.get(cache_key)

        if cached is not None:
            return cached

        precomputed = PrecomputedMissionData(waypoints=list(waypoints))
        precomputed.compute(self.distance_cache)
        precomputed.terrain_elevations = [None] * len(waypoints)

        if terrain_data is not None:
            await self._populate_terrain(precomputed, terrain_data)

        self._precomputed[cache_key] = precomputed
        return precomputed

    async def _populate_terrain(self, data: PrecomputedMissionData, terrain_data: Any) -> None:
        missing: list[tuple[int, tuple[float, float]]] = []

        for idx, wp in enumerate(data.waypoints):
            coord = _lat_lon(wp)

            if coord is None:
                continue

            cached = self.terrain_cache.get(coord[0], coord[1])

            if cached is None:
                missing.append((idx, coord))
            else:
                data.terrain_elevations[idx] = cached

        if not missing:
            return

        batch_fn = getattr(terrain_data, "elevations_m", None) or getattr(
            terrain_data,
            "get_elevations",
            None,
        )

        if batch_fn is not None:
            chunk_size = int(getattr(terrain_data, "max_batch_size", 250) or 250)

            for start in range(0, len(missing), chunk_size):
                chunk = missing[start : start + chunk_size]
                coords = [coord for _, coord in chunk]
                result = await self._call_maybe_async(batch_fn, coords)

                for offset, (idx, coord) in enumerate(chunk):
                    elevation = self._value_from_batch_result(result, coord, offset)

                    if elevation is not None:
                        elevation_f = float(elevation)
                        data.terrain_elevations[idx] = elevation_f
                        self.terrain_cache.set(coord[0], coord[1], elevation_f)

            return

        single_fn = getattr(terrain_data, "get_elevation", None)

        if single_fn is None:
            return

        async def fetch_one(idx: int, coord: tuple[float, float]) -> None:
            elevation = await self._call_maybe_async(single_fn, coord[0], coord[1])

            if elevation is not None:
                elevation_f = float(elevation)
                data.terrain_elevations[idx] = elevation_f
                self.terrain_cache.set(coord[0], coord[1], elevation_f)

        await asyncio.gather(*(fetch_one(idx, coord) for idx, coord in missing))

    def clear(self) -> None:
        self.terrain_cache.clear()
        self.distance_cache.clear()
        self._precomputed.clear()
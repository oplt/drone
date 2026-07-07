from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.modules.missions.schemas.mission_types import Mission, Waypoint

from .async_invocation import call_maybe_async
from .cache import DistanceCache, TerrainCache, optimized_distance
from .check_models import PrecomputedMissionData


@dataclass
class PreflightContext:
    vehicle_state: Any
    mission: Mission
    timestamp: float = field(default_factory=time.time)

    terrain_provider: Any | None = None
    wind_data: dict[str, float] | None = None
    weather_data: dict[str, object] | None = None
    weather_api_error: str | None = None
    no_fly_zones: list[Any] | None = None
    obstacle_map: Any | None = None
    geofence_polygon: list[Waypoint] | None = None

    precomputed: PrecomputedMissionData | None = None
    terrain_cache: TerrainCache | None = None
    distance_cache: DistanceCache | None = None
    config_overrides: dict[str, Any] = field(default_factory=dict)

    vehicle_id: str | None = None
    flight_id: str | None = None

    _terrain_cache: TerrainCache = field(init=False, repr=False)
    _distance_cache: DistanceCache = field(init=False, repr=False)
    _computed_segment_distances: list[float] = field(default_factory=list, init=False, repr=False)
    _computed_total_distance: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.config_overrides = self.config_overrides or {}
        self._terrain_cache = self.terrain_cache or TerrainCache()
        self._distance_cache = self.distance_cache or DistanceCache()

        if self.precomputed is None and self._waypoints:
            self._precompute_distances()

    @property
    def _waypoints(self) -> list[Any]:
        return list(getattr(self.mission, "waypoints", []) or [])

    def _precompute_distances(self) -> None:
        self._computed_segment_distances = []
        total = 0.0

        for a, b in zip(self._waypoints, self._waypoints[1:]):
            if not all(hasattr(p, "lat") and hasattr(p, "lon") for p in (a, b)):
                continue

            dist = self._distance_cache.get(a.lat, a.lon, b.lat, b.lon)

            if dist is None:
                dist = optimized_distance(a.lat, a.lon, b.lat, b.lon)
                self._distance_cache.set(a.lat, a.lon, b.lat, b.lon, dist)

            self._computed_segment_distances.append(dist)
            total += dist

        self._computed_total_distance = total

    def get_distance(self, idx1: int, idx2: int) -> float:
        if idx1 == idx2:
            return 0.0

        start, end = sorted((idx1, idx2))

        if start < 0 or end >= len(self._waypoints):
            raise IndexError(f"Waypoint index out of range: {idx1}, {idx2}")

        if self.precomputed is not None:
            return self.precomputed.get_distance_between(start, end)

        return sum(self._computed_segment_distances[start:end])

    def get_distance_between_points(self, wp1: Waypoint, wp2: Waypoint) -> float:
        cached = self._distance_cache.get(wp1.lat, wp1.lon, wp2.lat, wp2.lon)

        if cached is not None:
            return cached

        distance = optimized_distance(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
        self._distance_cache.set(wp1.lat, wp1.lon, wp2.lat, wp2.lon, distance)
        return distance

    def total_distance(self) -> float:
        if self.precomputed is not None:
            return self.precomputed.total_distance

        return self._computed_total_distance

    async def get_terrain_elevation(self, lat: float, lon: float) -> float | None:
        cached = self._terrain_cache.get(lat, lon)

        if cached is not None:
            return cached

        if self.terrain_provider is None:
            return None

        fetcher = getattr(self.terrain_provider, "get_elevation", None)

        if fetcher is None:
            return None

        elevation = await call_maybe_async(fetcher, lat, lon)

        if elevation is not None:
            elevation = float(elevation)
            self._terrain_cache.set(lat, lon, elevation)

        return elevation

    def get_waypoint_terrain(self, idx: int) -> float | None:
        waypoints = self._waypoints

        if idx < 0 or idx >= len(waypoints):
            return None

        if self.precomputed is not None:
            return self.precomputed.get_terrain_at(idx)

        wp = waypoints[idx]

        if not hasattr(wp, "lat") or not hasattr(wp, "lon"):
            return None

        return self._terrain_cache.get(wp.lat, wp.lon)

    async def get_waypoint_terrain_async(self, idx: int) -> float | None:
        waypoints = self._waypoints

        if idx < 0 or idx >= len(waypoints):
            return None

        terrain = self.get_waypoint_terrain(idx)

        if terrain is not None:
            return terrain

        wp = waypoints[idx]

        if not hasattr(wp, "lat") or not hasattr(wp, "lon"):
            return None

        return await self.get_terrain_elevation(wp.lat, wp.lon)

    def get_wind_speed(self) -> float | None:
        return None if not self.wind_data else self.wind_data.get("speed")

    def get_wind_gust(self) -> float | None:
        return None if not self.wind_data else self.wind_data.get("gust")

    def get_wind_direction(self) -> float | None:
        return None if not self.wind_data else self.wind_data.get("direction")

    def get_weather_snapshot(self) -> dict[str, object] | None:
        return self.weather_data

    def check_no_fly_zones(self, lat: float, lon: float, buffer: float = 0) -> bool:
        if not self.no_fly_zones:
            return True

        for zone in self.no_fly_zones:
            contains = getattr(zone, "contains", None)

            if contains is None:
                continue

            try:
                if contains(lat, lon, buffer):
                    return False
            except TypeError:
                try:
                    if contains((lon, lat)):
                        return False
                except Exception:
                    continue

        return True

    def get_config(self, key: str, default: Any = None) -> Any:
        if key in self.config_overrides:
            return self.config_overrides[key]

        config = None

        if isinstance(self.vehicle_state, dict):
            config = self.vehicle_state.get("config")
        else:
            config = getattr(self.vehicle_state, "config", None)

        if isinstance(config, dict) and key in config:
            return config[key]

        return default

    def get_threshold(self, name: str, default: Any) -> Any:
        return self.get_config(name, default)

    @property
    def cache_stats(self) -> dict[str, Any]:
        return {
            "terrain_cache": self._terrain_cache.stats,
            "distance_cache": self._distance_cache.stats,
        }

    def clear_caches(self) -> None:
        self._terrain_cache.clear()
        self._distance_cache.clear()
        self._computed_segment_distances.clear()
        self._computed_total_distance = 0.0

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
import time
from ..missions.schemas import Mission, Waypoint
from .cache import TerrainCache, DistanceCache, optimized_distance
from .models import PrecomputedMissionData



@dataclass
class PreflightContext:
    """
    Central context object containing all data needed for preflight checks.
    This is passed to all checkers, ensuring consistent access to data and cached computations.
    """

    # Core data
    vehicle_state: Any  # Vehicle telemetry snapshot
    mission: Mission     # Validated mission object
    timestamp: float = field(default_factory=time.time)

    # Optional data providers
    terrain_provider: Optional[Any] = None  # Terrain data provider with get_elevation(lat, lon)
    wind_data: Optional[Dict[str, float]] = None  # Wind speed, gust, direction
    no_fly_zones: Optional[List[Any]] = None  # List of no-fly zones
    obstacle_map: Optional[Any] = None  # Obstacle map data
    geofence_polygon: Optional[List[Waypoint]] = None  # Geofence boundary

    # Precomputed/cached data
    precomputed: Optional[PrecomputedMissionData] = None
    terrain_cache: Optional[TerrainCache] = None
    distance_cache: Optional[DistanceCache] = None

    # Configuration overrides
    config_overrides: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    vehicle_id: Optional[str] = None
    flight_id: Optional[str] = None

    # Internal caches (initialized if not provided)
    _terrain_cache: TerrainCache = field(init=False, repr=False)
    _distance_cache: DistanceCache = field(init=False, repr=False)
    _computed_segment_distances: List[float] = field(default_factory=list, init=False, repr=False)
    _computed_total_distance: float = field(default=0.0, init=False, repr=False)


    def __post_init__(self):
        """Initialize internal caches if not provided."""
        # Ensure config_overrides is never None
        if self.config_overrides is None:
            self.config_overrides = {}

        if self.terrain_cache is None:
            self._terrain_cache = TerrainCache()
        else:
            self._terrain_cache = self.terrain_cache

        if self.distance_cache is None:
            self._distance_cache = DistanceCache()
        else:
            self._distance_cache = self.distance_cache

        # Precompute distances if waypoints exist and no precomputed data
        if self.mission and self.mission.waypoints and self.precomputed is None:
            self._precompute_distances()


    def _precompute_distances(self):
        """Precompute all segment distances."""
        waypoints = self.mission.waypoints
        self._computed_segment_distances = []
        total = 0.0

        for i in range(len(waypoints) - 1):
            wp1 = waypoints[i]
            wp2 = waypoints[i + 1]

            # Check cache first
            dist = self._distance_cache.get(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
            if dist is None:
                dist = optimized_distance(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
                self._distance_cache.set(wp1.lat, wp1.lon, wp2.lat, wp2.lon, dist)

            self._computed_segment_distances.append(dist)
            total += dist

        self._computed_total_distance = total

    # ========== Distance methods ==========

    def get_distance(self, idx1: int, idx2: int) -> float:
        """
        Get distance between two waypoints by index.
        Uses cached/precomputed values when available.
        """
        if self.precomputed:
            return self.precomputed.get_distance_between(min(idx1, idx2), max(idx1, idx2))

        # Use precomputed segment distances
        if idx1 == idx2:
            return 0.0

        start, end = min(idx1, idx2), max(idx1, idx2)
        if end - start == 1 and start < len(self._computed_segment_distances):
            return self._computed_segment_distances[start]

        # Sum segment distances
        total = 0.0
        for i in range(start, end):
            if i < len(self._computed_segment_distances):
                total += self._computed_segment_distances[i]
            else:
                # Fallback to on-demand calculation
                wp1 = self.mission.waypoints[i]
                wp2 = self.mission.waypoints[i + 1]
                total += self.get_distance_between_points(wp1, wp2)

        return total

    def get_distance_between_points(self, wp1: Waypoint, wp2: Waypoint) -> float:
        """Get distance between two waypoint objects with caching."""
        # Check cache
        dist = self._distance_cache.get(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
        if dist is not None:
            return dist

        # Compute and cache
        dist = optimized_distance(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
        self._distance_cache.set(wp1.lat, wp1.lon, wp2.lat, wp2.lon, dist)
        return dist

    def total_distance(self) -> float:
        """Get total mission distance."""
        if self.precomputed:
            return self.precomputed.total_distance
        return self._computed_total_distance


    async def get_terrain_elevation(self, lat: float, lon: float) -> Optional[float]:
        """Async terrain fetch with cache."""
        # Try precomputed first
        if self.precomputed:
            for i, wp in enumerate(self.mission.waypoints):
                if abs(wp.lat - lat) < 1e-6 and abs(wp.lon - lon) < 1e-6:
                    return self.precomputed.get_terrain_at(i)

        # Try cache
        elev = self._terrain_cache.get(lat, lon)
        if elev is not None:
            return elev

        # Async fetch from provider
        if self.terrain_provider and hasattr(self.terrain_provider, 'get_elevation'):
            elev = await self.terrain_provider.get_elevation(lat, lon)
            if elev is not None:
                self._terrain_cache.set(lat, lon, elev)
            return elev

        return None

    def get_waypoint_terrain(self, idx: int) -> Optional[float]:
        """Get terrain elevation for a specific waypoint."""
        if idx >= len(self.mission.waypoints):
            return None

        wp = self.mission.waypoints[idx]

        if self.precomputed:
            return self.precomputed.get_terrain_at(idx)

        return self.get_terrain_elevation(wp.lat, wp.lon)

    # ========== Wind methods ==========

    def get_wind_speed(self) -> Optional[float]:
        """Get current wind speed."""
        if self.wind_data:
            return self.wind_data.get('speed')
        return None

    def get_wind_gust(self) -> Optional[float]:
        """Get wind gust speed."""
        if self.wind_data:
            return self.wind_data.get('gust')
        return None

    def get_wind_direction(self) -> Optional[float]:
        """Get wind direction in degrees."""
        if self.wind_data:
            return self.wind_data.get('direction')
        return None

    # ========== No-fly zone methods ==========

    def check_no_fly_zones(self, lat: float, lon: float, buffer: float = 0) -> bool:
        """
        Check if a point is inside any no-fly zone.
        Returns True if point is safe (outside all zones).
        """
        if not self.no_fly_zones:
            return True

        # This would need actual geometry checking
        # Placeholder implementation
        for zone in self.no_fly_zones:
            if hasattr(zone, 'contains') and zone.contains(lat, lon, buffer):
                return False

        return True

    # ========== Configuration ==========

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value with override support."""
        if key in self.config_overrides:
            return self.config_overrides[key]

        # Check vehicle state for config
        if hasattr(self.vehicle_state, 'config') and key in self.vehicle_state.config:
            return self.vehicle_state.config[key]

        return default

    # ========== Utility methods ==========

    def get_threshold(self, name: str, default: float) -> float:
        """Get threshold value from config overrides."""
        return self.get_config(name, default)

    @property
    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'terrain_cache': self._terrain_cache.stats,
            'distance_cache': self._distance_cache.stats
        }

    def clear_caches(self):
        """Clear all internal caches."""
        self._terrain_cache.clear()
        self._distance_cache = DistanceCache()
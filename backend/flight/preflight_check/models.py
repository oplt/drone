# drone/preflight/models.py

import hashlib
import json
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class PrecomputedMissionData:
    """
    Precomputed mission data to avoid repeated calculations.
    """
    waypoints: List[Any]  # Original waypoints
    segment_distances: List[float] = field(default_factory=list)
    cumulative_distances: List[float] = field(default_factory=list)
    terrain_elevations: List[Optional[float]] = field(default_factory=list)
    bearings: List[float] = field(default_factory=list)
    total_distance: float = 0.0
    estimated_duration: float = 0.0

    def __post_init__(self):
        """Compute all distances and bearings."""
        if self.waypoints and len(self.waypoints) > 0:
            self._compute_distances()
            self._compute_bearings()

    def _compute_distances(self):
        """Compute all segment distances."""
        self.segment_distances = []
        self.cumulative_distances = [0.0]

        for i in range(len(self.waypoints) - 1):
            wp1 = self.waypoints[i]
            wp2 = self.waypoints[i + 1]

            # Use optimized distance calculation
            from .cache import optimized_distance
            dist = optimized_distance(wp1.lat, wp1.lon, wp2.lat, wp2.lon)
            self.segment_distances.append(dist)
            self.cumulative_distances.append(self.cumulative_distances[-1] + dist)

        self.total_distance = self.cumulative_distances[-1] if self.cumulative_distances else 0

    def _compute_bearings(self):
        """Compute initial bearings for each segment."""
        from math import atan2, sin, cos, radians

        self.bearings = []
        for i in range(len(self.waypoints) - 1):
            wp1 = self.waypoints[i]
            wp2 = self.waypoints[i + 1]

            lat1 = radians(wp1.lat)
            lat2 = radians(wp2.lat)
            dlon = radians(wp2.lon - wp1.lon)

            y = sin(dlon) * cos(lat2)
            x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
            bearing = atan2(y, x)
            self.bearings.append(bearing)

    def get_segment_distance(self, idx: int) -> float:
        """Get distance for a specific segment."""
        if 0 <= idx < len(self.segment_distances):
            return self.segment_distances[idx]
        raise IndexError(f"Segment index {idx} out of range")

    def get_distance_between(self, start_idx: int, end_idx: int) -> float:
        """Get cumulative distance between two waypoint indices."""
        # BUG FIX: also guard start_idx against the upper bound
        if (start_idx < 0
                or start_idx >= len(self.cumulative_distances)
                or end_idx >= len(self.cumulative_distances)):
            raise IndexError(
                f"Index out of range: start={start_idx}, end={end_idx}, "
                f"cumulative_distances length={len(self.cumulative_distances)}"
            )
        return abs(self.cumulative_distances[end_idx] - self.cumulative_distances[start_idx])

    def get_terrain_at(self, idx: int) -> Optional[float]:
        """Get terrain elevation at waypoint index."""
        if 0 <= idx < len(self.terrain_elevations):
            return self.terrain_elevations[idx]
        return None


class MissionDataPreprocessor:
    """
    Preprocessor that computes all mission data once and caches it.
    """

    def __init__(self, terrain_cache=None):
        # BUG FIX: import at class level so clear() can also use DistanceCache
        from .cache import TerrainCache, DistanceCache
        self.terrain_cache = terrain_cache or TerrainCache()
        self.distance_cache = DistanceCache()
        self._precomputed: Dict[str, PrecomputedMissionData] = {}

    def preprocess(self, waypoints: List[Any], terrain_data=None) -> PrecomputedMissionData:
        """
        Precompute all mission data.

        Args:
            waypoints: List of waypoints
            terrain_data: Optional terrain data provider

        Returns:
            PrecomputedMissionData object
        """
        # Create a hash of the waypoints for caching
        wp_summary = [(w.lat, w.lon, getattr(w, 'alt', 0)) for w in waypoints]
        cache_key = hashlib.md5(json.dumps(wp_summary).encode()).hexdigest()

        # Return cached if available
        if cache_key in self._precomputed:
            return self._precomputed[cache_key]

        # Create new precomputed data
        precomputed = PrecomputedMissionData(waypoints=waypoints)

        # Precompute terrain elevations if terrain data available
        if terrain_data and hasattr(terrain_data, 'get_elevation'):
            for wp in waypoints:
                # Check cache first
                elev = self.terrain_cache.get(wp.lat, wp.lon)
                if elev is None:
                    # Fetch from terrain data
                    try:
                        elev = terrain_data.get_elevation(wp.lat, wp.lon)
                        if elev is not None:
                            self.terrain_cache.set(wp.lat, wp.lon, elev)
                    except Exception:
                        elev = None
                precomputed.terrain_elevations.append(elev)
        else:
            # Fill with None if no terrain data
            precomputed.terrain_elevations = [None] * len(waypoints)

        # Cache the result
        self._precomputed[cache_key] = precomputed
        return precomputed

    def clear(self):
        """Clear all caches."""
        # BUG FIX: import DistanceCache here so it is in scope
        from .cache import DistanceCache
        self.terrain_cache.clear()
        self.distance_cache = DistanceCache()
        self._precomputed.clear()
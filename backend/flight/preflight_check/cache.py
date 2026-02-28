from typing import Dict, Tuple, Optional
import time
from backend.utils.geo import haversine_km
import asyncio


class TerrainCache:
    """
    Cache for terrain elevation data to avoid repeated API calls.
    Rounds coordinates to ~1m precision (1e-5 degrees ≈ 1.1m at equator).
    """

    def __init__(self, precision: float = 1e-5, ttl_seconds: Optional[float] = 300):
        """
        Initialize terrain cache.

        Args:
            precision: Coordinate rounding precision in degrees
            ttl_seconds: Time-to-live for cache entries (None = no expiry)
        """
        self.precision = precision
        self.ttl = ttl_seconds
        self._cache: Dict[str, Tuple[float, float]] = {}  # key -> (elevation, timestamp)
        self._hits = 0
        self._misses = 0

    def _make_key(self, lat: float, lon: float) -> str:
        """Create cache key from rounded coordinates."""
        # Determine decimal places from precision (e.g. 1e-5 -> 5 places)
        import math
        decimal_places = max(0, -int(math.floor(math.log10(self.precision))))
        rounded_lat = round(lat, decimal_places)
        rounded_lon = round(lon, decimal_places)
        fmt = f"{{:.{decimal_places}f}}"
        return f"{fmt.format(rounded_lat)},{fmt.format(rounded_lon)}"

    def get(self, lat: float, lon: float) -> Optional[float]:
        """Get cached elevation if available and not expired."""
        key = self._make_key(lat, lon)
        if key in self._cache:
            elevation, timestamp = self._cache[key]
            if self.ttl is None or (time.time() - timestamp) < self.ttl:
                self._hits += 1
                return elevation
            else:
                # Expired
                del self._cache[key]
        self._misses += 1
        return None

    def set(self, lat: float, lon: float, elevation: float):
        """Cache elevation for coordinates."""
        key = self._make_key(lat, lon)
        self._cache[key] = (elevation, time.time())

    def clear(self):
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0
        }


    async def get_or_fetch(
            self,
            lat: float,
            lon: float,
            fetcher  # async callable: async def(lat, lon) -> float | None
    ) -> Optional[float]:
        """Get from cache or fetch asynchronously."""
        cached = self.get(lat, lon)
        if cached is not None:
            return cached
        elevation = await fetcher(lat, lon)
        if elevation is not None:
            self.set(lat, lon, elevation)
        return elevation


class DistanceCache:
    """
    Cache for haversine distances between coordinate pairs.
    """

    def __init__(self):
        self._cache: Dict[str, float] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, lat1: float, lon1: float, lat2: float, lon2: float) -> str:
        """Create cache key (order-independent for pairs)."""
        # Sort coordinates to make key order-independent
        coords = sorted([
            (round(lat1, 6), round(lon1, 6)),
            (round(lat2, 6), round(lon2, 6))
        ])
        return f"{coords[0][0]},{coords[0][1]}|{coords[1][0]},{coords[1][1]}"

    def get(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
        """Get cached distance if available."""
        key = self._make_key(lat1, lon1, lat2, lon2)
        if key in self._cache:
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, lat1: float, lon1: float, lat2: float, lon2: float, distance: float):
        """Cache distance for coordinate pair."""
        key = self._make_key(lat1, lon1, lat2, lon2)
        self._cache[key] = distance

    @property
    def stats(self) -> Dict[str, any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0
        }


# Fast local projection for small distances (< 10km)
def fast_local_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Fast distance approximation using equirectangular projection.
    Accurate enough for distances < 10km, ~50x faster than haversine.
    """
    from math import radians, cos, sqrt

    # Convert to radians
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    # Equirectangular approximation
    x = (lon2_rad - lon1_rad) * cos((lat1_rad + lat2_rad) / 2)
    y = lat2_rad - lat1_rad

    # Earth radius in meters
    R = 6371000
    return R * sqrt(x*x + y*y)


def optimized_distance(lat1: float, lon1: float, lat2: float, lon2: float,
                       threshold: float = 0.1) -> float:
    """
    Optimized distance calculation using fast approximation for small distances.

    Args:
        threshold: Distance threshold in degrees (~11km at equator)
    """
    # Quick check if points are far apart using rough approximation
    if abs(lat1 - lat2) > threshold or abs(lon1 - lon2) > threshold:
        dist_km = haversine_km(lat1, lon1, lat2, lon2)
        dist_meter = dist_km * 1000
        return dist_meter
    else:
        return fast_local_distance(lat1, lon1, lat2, lon2)
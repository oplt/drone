from __future__ import annotations

from collections import OrderedDict
import threading

import googlemaps
from backend.drone.models import Coordinate


class GoogleMapsClient:
    def __init__(
        self,
        api_key: str,
        *,
        elevation_cache_precision_deg: float = 1e-5,
        elevation_cache_max_entries: int = 20_000,
        elevation_batch_size: int = 250,
    ):
        self.client = googlemaps.Client(api_key)
        self._elevation_cache_precision_deg = max(1e-7, float(elevation_cache_precision_deg))
        self._elevation_cache_max_entries = max(1, int(elevation_cache_max_entries))
        self._elevation_batch_size = max(1, int(elevation_batch_size))
        self._elevation_cache: OrderedDict[tuple[int, int], float] = OrderedDict()
        self._elevation_cache_lock = threading.Lock()

    def _elevation_cache_key(self, lat: float, lon: float) -> tuple[int, int]:
        precision = self._elevation_cache_precision_deg
        return (
            int(round(float(lat) / precision)),
            int(round(float(lon) / precision)),
        )

    def _elevation_cache_get(self, key: tuple[int, int]) -> float | None:
        with self._elevation_cache_lock:
            value = self._elevation_cache.get(key)
            if value is None:
                return None
            self._elevation_cache.move_to_end(key)
            return value

    def _elevation_cache_set(self, key: tuple[int, int], value: float) -> None:
        with self._elevation_cache_lock:
            self._elevation_cache[key] = value
            self._elevation_cache.move_to_end(key)
            while len(self._elevation_cache) > self._elevation_cache_max_entries:
                self._elevation_cache.popitem(last=False)

    def _chunked(self, coords: list[tuple[float, float]]):
        for idx in range(0, len(coords), self._elevation_batch_size):
            yield coords[idx:idx + self._elevation_batch_size]

    def geocode(self, address: str) -> Coordinate:
        res = self.client.geocode(address)
        loc = res[0]["geometry"]["location"]
        return Coordinate(lat=loc["lat"], lon=loc["lng"])

    def waypoints_between(self, start: Coordinate, end: Coordinate, steps: int = 5):
        if steps <= 0:
            raise ValueError("steps must be > 0")
        dlat = (end.lat - start.lat) / steps
        dlon = (end.lon - start.lon) / steps
        for i in range(1, steps + 1):
            yield Coordinate(
                lat=start.lat + dlat * i,
                lon=start.lon + dlon * i,
                alt=end.alt,
            )

    # ✅ NEW: Google Elevation API (single)
    def elevation_m(self, lat: float, lon: float) -> float:
        return self.elevations_m([(lat, lon)])[0]

    # ✅ NEW: Google Elevation API (batch)
    def elevations_m(self, coords: list[tuple[float, float]]) -> list[float]:
        # coords: [(lat, lon), ...]
        if not coords:
            return []

        out: list[float | None] = [None] * len(coords)
        missing_by_key: dict[tuple[int, int], list[int]] = {}
        missing_coords: list[tuple[float, float]] = []

        for idx, (lat, lon) in enumerate(coords):
            key = self._elevation_cache_key(lat, lon)
            cached = self._elevation_cache_get(key)
            if cached is not None:
                out[idx] = cached
                continue
            if key not in missing_by_key:
                missing_by_key[key] = [idx]
                missing_coords.append((float(lat), float(lon)))
            else:
                missing_by_key[key].append(idx)

        for chunk in self._chunked(missing_coords):
            res = self.client.elevation(chunk)
            if not res or len(res) != len(chunk):
                raise RuntimeError("Elevation batch returned unexpected result length")

            for local_idx, row in enumerate(res):
                value = float(row["elevation"])
                lat, lon = chunk[local_idx]
                key = self._elevation_cache_key(lat, lon)
                self._elevation_cache_set(key, value)
                for original_idx in missing_by_key[key]:
                    out[original_idx] = value

        if any(value is None for value in out):
            raise RuntimeError("Elevation lookup left unresolved coordinates")

        return [float(value) for value in out]

    # Compatibility aliases used in older mission and preflight flows.
    def get_elevation(self, lat: float, lon: float) -> float:
        return self.elevation_m(lat, lon)

    def get_elevations(self, coords: list[tuple[float, float]]) -> list[float]:
        return self.elevations_m(coords)

    def elevation(self, lat: float, lon: float) -> float:
        return self.elevation_m(lat, lon)

    def elevation_at(self, lat: float, lon: float) -> float:
        return self.elevation_m(lat, lon)

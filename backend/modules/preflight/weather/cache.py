from __future__ import annotations

import asyncio
from typing import TypeVar

from backend.infrastructure.cache.local import BoundedTTLCache

T = TypeVar("T")


class WeatherResponseCache:
    """Short-lived in-memory cache keyed by rounded lat/lon."""

    def __init__(self, *, max_entries: int = 256) -> None:
        self._entries = BoundedTTLCache[T](max_entries=max_entries)
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(lat: float, lon: float) -> str:
        return f"{round(lat, 3):.3f},{round(lon, 3):.3f}"

    async def get(self, lat: float, lon: float, *, ttl_s: float) -> T | None:
        key = self._key(lat, lon)
        async with self._lock:
            return self._entries.get(key, ttl_seconds=ttl_s)

    async def set(self, lat: float, lon: float, value: T) -> None:
        key = self._key(lat, lon)
        async with self._lock:
            self._entries.set(key, value)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


_weather_cache = WeatherResponseCache()

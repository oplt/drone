from __future__ import annotations

import asyncio
import time
from typing import TypeVar

T = TypeVar("T")


class WeatherResponseCache:
    """Short-lived in-memory cache keyed by rounded lat/lon."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, T]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(lat: float, lon: float) -> str:
        return f"{round(lat, 3):.3f},{round(lon, 3):.3f}"

    async def get(self, lat: float, lon: float, *, ttl_s: float) -> T | None:
        key = self._key(lat, lon)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            cached_at, value = entry
            if time.time() - cached_at > ttl_s:
                self._entries.pop(key, None)
                return None
            return value

    async def set(self, lat: float, lon: float, value: T) -> None:
        key = self._key(lat, lon)
        async with self._lock:
            self._entries[key] = (time.time(), value)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


_weather_cache = WeatherResponseCache()

"""Small bounded in-process caches for non-authoritative read-through data."""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


class BoundedTTLCache(Generic[T]):
    """Thread-safe LRU/TTL cache; never use this for durable or safety state."""

    def __init__(self, *, max_entries: int, ttl_seconds: float | None = None) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[object, tuple[float, T]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: object, *, ttl_seconds: float | None = None) -> T | None:
        now = time.monotonic()
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if ttl is not None and now - stored_at >= max(0.0, ttl):
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: object, value: T) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def pop(self, key: object) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

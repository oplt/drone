from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from pathlib import Path

from backend.modules.warehouse.service.live_map_stream import WarehouseLiveMapSnapshot

SnapshotCacheKey = tuple[str, str, tuple[str, ...]]
SnapshotSignature = tuple[int, int, int]


class DiskLiveMapSnapshotCache:
    """Small process-local LRU keyed by immutable flight-directory state."""

    def __init__(self, *, max_entries: int = 64) -> None:
        self._max_entries = max(1, max_entries)
        self._entries: OrderedDict[
            SnapshotCacheKey,
            tuple[float, SnapshotSignature, WarehouseLiveMapSnapshot],
        ] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def signature(root: Path) -> SnapshotSignature | None:
        try:
            root_stat = root.stat()
        except OSError:
            return None
        manifest = root / "live_map_manifest.json"
        try:
            manifest_stat = manifest.stat()
            return (
                root_stat.st_mtime_ns,
                manifest_stat.st_mtime_ns,
                manifest_stat.st_size,
            )
        except OSError:
            return (root_stat.st_mtime_ns, 0, 0)

    def get(
        self,
        key: SnapshotCacheKey,
        *,
        signature: SnapshotSignature,
        ttl_s: float,
    ) -> WarehouseLiveMapSnapshot | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            cached_at, cached_signature, snapshot = entry
            if ttl_s <= 0 or now - cached_at >= ttl_s or cached_signature != signature:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return copy.deepcopy(snapshot)

    def put(
        self,
        key: SnapshotCacheKey,
        *,
        signature: SnapshotSignature,
        snapshot: WarehouseLiveMapSnapshot,
    ) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), signature, copy.deepcopy(snapshot))
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


disk_live_map_snapshot_cache = DiskLiveMapSnapshotCache()

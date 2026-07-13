"""Shared runtime helpers for deterministic geometry algorithms.

Planner caches are intentionally opt-in and bounded.  Cache keys include the
algorithm version and a canonical representation of every input, so changing
the algorithm cannot reuse stale routes.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from threading import Lock
from typing import Any, TypeVar

from backend.observability.profiling import profile_stage

T = TypeVar("T")

GEOMETRY_ALGORITHM_VERSION = "geometry-2026-07-13-v1"


def normalized_algorithm_key(
    namespace: str, algorithm_version: str, payload: Any
) -> str:
    """Return a stable, bounded key for pure algorithm inputs."""
    if is_dataclass(payload):
        payload = asdict(payload)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{namespace}:{algorithm_version}:{digest}"


class PurePlanCache:
    """Small process-local cache for pure plans; no cache is used for I/O."""

    def __init__(self, *, max_entries: int = 128) -> None:
        self.max_entries = max(1, int(max_entries))
        self._items: OrderedDict[str, Any] = OrderedDict()
        self._lock = Lock()

    def get_or_compute(
        self,
        *,
        namespace: str,
        algorithm_version: str,
        payload: Any,
        compute: Callable[[], T],
        workload: str,
    ) -> T:
        key = normalized_algorithm_key(namespace, algorithm_version, payload)
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return copy.deepcopy(self._items[key])

        with profile_stage(namespace, workload=workload):
            result = compute()
        with self._lock:
            self._items[key] = copy.deepcopy(result)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
        return result


def workload_label(*, vertices: int, obstacles: int = 0, retries: int = 0) -> str:
    return (
        f"vertices={max(0, int(vertices))};"
        f"obstacles={max(0, int(obstacles))};retries={max(0, int(retries))}"
    )


def profiled_geometry_plan(namespace: str):
    """Profile a pure planner while keeping workload dimensions observable."""

    def decorate(function: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> T:
            polygon = kwargs.get("polygon_lonlat")
            if polygon is None and args:
                polygon = args[0]
            vertices = len(polygon) if hasattr(polygon, "__len__") else 0
            payload = {"args": args, "kwargs": kwargs}
            return geometry_plan_cache.get_or_compute(
                namespace=namespace,
                algorithm_version=GEOMETRY_ALGORITHM_VERSION,
                payload=payload,
                workload=workload_label(vertices=vertices),
                compute=lambda: function(*args, **kwargs),
            )

        return wrapped

    return decorate


geometry_plan_cache = PurePlanCache()

from __future__ import annotations

import asyncio
import math
from typing import Any, Callable, Iterable, Sequence

from backend.drone.models import Coordinate

def _chunked(items: Sequence[tuple[float, float]], size: int) -> Iterable[Sequence[tuple[float, float]]]:
    if size <= 0:
        size = 1
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _call_single_elevation(fn: Callable[..., Any], lat: float, lon: float) -> float:
    try:
        return float(fn(lat, lon))
    except TypeError:
        try:
            return float(fn(lat=lat, lon=lon))
        except TypeError:
            return float(fn((lat, lon)))


def _batch_elevations_m(maps_client: Any, coords: Sequence[tuple[float, float]]) -> list[float]:
    if not coords:
        return []

    for attr in ("elevations_m", "get_elevations", "elevation_many_m"):
        fn = getattr(maps_client, attr, None)
        if not callable(fn):
            continue
        try:
            values = fn(list(coords))
        except TypeError:
            values = fn(coords=list(coords))
        return [float(v) for v in values]

    for attr in ("elevation_m", "get_elevation", "elevation_at", "elevation"):
        fn = getattr(maps_client, attr, None)
        if not callable(fn):
            continue
        return [_call_single_elevation(fn, lat, lon) for lat, lon in coords]

    raise RuntimeError("No elevation provider found on maps client")


async def elevations_for_path_m(
    *,
    maps_client: Any,
    path: Sequence[Coordinate],
    batch_size: int = 250,
) -> list[float]:
    latlon = [(p.lat, p.lon) for p in path]
    if not latlon:
        return []

    values: list[float] = []
    for batch in _chunked(latlon, batch_size):
        part = await asyncio.to_thread(_batch_elevations_m, maps_client, batch)
        if len(part) != len(batch):
            raise RuntimeError(
                f"Elevation batch length mismatch: got {len(part)}, expected {len(batch)}"
            )
        values.extend(part)
    return values


def resolve_home_amsl_m(drone: Any) -> float:
    home = getattr(drone, "home_location", None)
    if home is not None:
        alt = getattr(home, "alt", None)
        if alt is not None:
            try:
                value = float(alt)
                if math.isfinite(value):
                    return value
            except (TypeError, ValueError):
                pass

    get_home_amsl = getattr(drone, "get_home_amsl", None)
    if callable(get_home_amsl):
        value = float(get_home_amsl())
        if math.isfinite(value):
            return value

    raise RuntimeError("Unable to resolve home AMSL altitude from drone adapter")


async def apply_terrain_follow_to_path(
    *,
    maps_client: Any,
    path: Sequence[Coordinate],
    home_amsl_m: float,
    target_agl_m: float,
    min_rel_alt_m: float = 10.0,
    max_rel_alt_m: float = 120.0,
    max_step_m: float = 3.0,
    batch_size: int = 250,
) -> list[Coordinate]:
    if not path:
        return []

    elevations_amsl = await elevations_for_path_m(
        maps_client=maps_client,
        path=path,
        batch_size=batch_size,
    )
    if len(elevations_amsl) != len(path):
        raise RuntimeError(
            f"Elevation/path length mismatch: {len(elevations_amsl)} vs {len(path)}"
        )

    out: list[Coordinate] = []
    prev_alt: float | None = None
    for point, ground_amsl in zip(path, elevations_amsl):
        alt_rel = (float(ground_amsl) - float(home_amsl_m)) + float(target_agl_m)
        alt_rel = max(float(min_rel_alt_m), min(float(max_rel_alt_m), alt_rel))

        if prev_alt is not None and max_step_m > 0:
            upper = prev_alt + float(max_step_m)
            lower = prev_alt - float(max_step_m)
            if alt_rel > upper:
                alt_rel = upper
            elif alt_rel < lower:
                alt_rel = lower

        out.append(Coordinate(lat=point.lat, lon=point.lon, alt=float(alt_rel)))
        prev_alt = alt_rel

    return out

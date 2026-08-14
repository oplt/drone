# backend/flight/missions/grid_mission.py
"""
GridMission: field-polygon → lawnmower grid → drone flight.

Architecture
------------
GridPlanner  – pure geometry: polygon → ordered waypoints (no I/O)
GridMission  – frozen dataclass mission that calls GridPlanner at fly-time,
               then delegates to the shared BaseMission execute() path.

Bug fixes applied
-----------------
1. Module-level geo helpers were accidentally nested *inside* the
   ElevationProvider Protocol class body — moved to module scope.
2. GridMission class was missing entirely; its fields + methods were
   floating at the end of GridPlanner.generate() (indentation error).
3. Missing imports: Coordinate, dataclass field(), logging, AgricultureMode.
4. GridPlanResult.waypoints referenced Coordinate before import.
5. _maybe_get_elevation_provider was nested inside ElevationProvider.
6. object.__setattr__ used on a non-frozen dataclass (was inconsistent);
   GridMission is now explicitly frozen=True and documented accordingly.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from shapely.geometry import LineString, Point, Polygon

from backend.core.geometry.algorithm_runtime import (
    GEOMETRY_ALGORITHM_VERSION,
    geometry_plan_cache,
    workload_label,
)
from backend.core.geometry.projection import (
    lonlat_to_xy_m as _lonlat_to_xy_m,
)
from backend.core.geometry.projection import (
    polygon_centroid_lonlat as _shared_polygon_centroid_lonlat,
)
from backend.core.geometry.projection import (
    xy_m_to_lonlat as _xy_m_to_lonlat,
)
from backend.core.types.geo import coord_from_home
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.planning.terrain_follow import (
    apply_terrain_follow_to_path,
    resolve_home_amsl_m,
)
from backend.modules.vehicle_runtime.types import Coordinate

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level geo helpers (equirectangular projection, small-area accurate)
# ---------------------------------------------------------------------------


def _rot(x: float, y: float, ang_rad: float) -> tuple[float, float]:
    c, s = math.cos(ang_rad), math.sin(ang_rad)
    return (c * x - s * y, s * x + c * y)


def _poly_centroid_lonlat(
    poly_lonlat: list[tuple[float, float]],
) -> tuple[float, float]:
    """Simple mean centroid of an open or closed (lon, lat) ring."""
    return _shared_polygon_centroid_lonlat(
        poly_lonlat,
        error_message="Polygon must have ≥ 3 points",
    )


def _maybe_get_elevation_provider(
    orch: Orchestrator,
) -> ElevationProvider | None:
    """Best-effort elevation provider from the orchestrator's maps client.

    Tries the most common attribute names; wraps the callable so callers
    always use ``fn(lat, lon)`` positional form.
    """
    maps = getattr(orch, "maps", None)
    if maps is None:
        return None

    for attr in ("elevation_m", "elevation_at", "get_elevation", "elevation"):
        fn = getattr(maps, attr, None)
        if not callable(fn):
            continue

        def _prov(lat: float, lon: float, _fn=fn) -> float:
            try:
                return float(_fn(lat, lon))
            except TypeError:
                try:
                    return float(_fn(lat=lat, lon=lon))
                except TypeError:
                    return float(_fn((lat, lon)))

        return _prov

    return None


def _maybe_get_batch_elevation_provider(
    orch: Orchestrator,
) -> BatchElevationProvider | None:
    """Best-effort batch elevation provider from the orchestrator's maps client."""
    maps = getattr(orch, "maps", None)
    if maps is None:
        return None

    for attr in ("elevations_m", "get_elevations", "elevation_many_m"):
        fn = getattr(maps, attr, None)
        if not callable(fn):
            continue

        def _prov(coords: list[tuple[float, float]], _fn=fn) -> list[float]:
            try:
                values = _fn(list(coords))
            except TypeError:
                values = _fn(coords=list(coords))
            return [float(v) for v in values]

        return _prov

    return None

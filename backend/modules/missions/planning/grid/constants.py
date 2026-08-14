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

AgricultureMode = Literal["mapping", "spray", "ndvi", "multispectral"]
MAX_GRID_ROWS = 1_000
MAX_GRID_WAYPOINTS = 2_200
MAX_GRID_ROUTE_M = 120_000.0
MAX_GRID_PATH_POINTS = 4_000

AgricultureMode = Literal["mapping", "spray", "ndvi", "multispectral"]
MAX_GRID_ROWS = 1_000
MAX_GRID_WAYPOINTS = 2_200
MAX_GRID_ROUTE_M = 120_000.0
MAX_GRID_PATH_POINTS = 4_000

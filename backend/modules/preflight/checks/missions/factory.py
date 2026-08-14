from __future__ import annotations

from ..context import PreflightContext
from .adaptive_altitude import AdaptiveAltitudeMissionPreflight
from .base import MissionPreflightBase
from .grid import GridMissionPreflight
from .indoor_exploration import IndoorExplorationMissionPreflight
from .orbit import OrbitMissionPreflight
from .perimeter_patrol import PerimeterPatrolMissionPreflight
from .terrain_follow import TerrainFollowMissionPreflight
from .warehouse_scan import WarehouseScanMissionPreflight
from .waypoint import WaypointMissionPreflight


def create_mission_preflight(context: PreflightContext) -> MissionPreflightBase:
    mission_type = str(getattr(context.mission, "type", "") or "").lower()

    aliases = {
        "survey": "grid",
        "circle": "orbit",
        "poi": "orbit",
        "private_patrol": "perimeter_patrol",
        "polygon": "perimeter_patrol",
        "patrol": "perimeter_patrol",
    }

    mission_type = aliases.get(mission_type, mission_type)

    mission_classes: dict[str, type[MissionPreflightBase]] = {
        "grid": GridMissionPreflight,
        "warehouse_scan": WarehouseScanMissionPreflight,
        "indoor_exploration": IndoorExplorationMissionPreflight,
        "terrain_follow": TerrainFollowMissionPreflight,
        "orbit": OrbitMissionPreflight,
        "perimeter_patrol": PerimeterPatrolMissionPreflight,
        "adaptive_altitude": AdaptiveAltitudeMissionPreflight,
        "route": WaypointMissionPreflight,
    }

    return mission_classes.get(mission_type, WaypointMissionPreflight)(context)

from __future__ import annotations

from typing import Literal

PatrolDirection = Literal["clockwise", "counterclockwise"]
PatrolTask = Literal[
    "intruder_detection",
    "vehicle_detection",
    "fence_breach_detection",
    "motion_detection",
]
PatrolResponseMode = Literal["incident_response", "detection_search"]
PatrolMissionTask = Literal[
    "perimeter_patrol",
    "waypoint_patrol",
    "grid_surveillance",
    "event_triggered_patrol",
]

MAX_PRIVATE_PATROL_PATH_POINTS = 4_000

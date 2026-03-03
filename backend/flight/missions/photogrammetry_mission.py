from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, List, Tuple
from backend.drone.models import Coordinate
from backend.drone.orchestrator import Orchestrator
import logging
from backend.services.photogrammetry.mission import make_photogrammetry_plan


logger = logging.getLogger(__name__)



@dataclass(frozen=True)
class PhotogrammetryMission:
    polygon_lonlat: List[Tuple[float, float]]  # [(lon,lat),...]
    altitude_agl: float
    fov_h: float
    fov_v: float
    front_overlap: float
    side_overlap: float
    heading_deg: float = 0.0

    mission_type: str = "photogrammetry"

    def get_waypoints(self) -> list[Coordinate]:
        plan = make_photogrammetry_plan(
            polygon_lonlat=self.polygon_lonlat,
            altitude_agl=self.altitude_agl,
            fov_h=self.fov_h,
            fov_v=self.fov_v,
            front_overlap=self.front_overlap,
            side_overlap=self.side_overlap,
            heading_deg=self.heading_deg,
        )
        return plan.waypoints

    async def execute(self, orch: Orchestrator, alt: float) -> None:
        # reuse the standard mission execution pipeline (preflight, telemetry, etc.) :contentReference[oaicite:23]{index=23}
        await orch.run_mission(self, alt=alt, flight_fn=lambda: orch.drone.follow_waypoints(self.get_waypoints()))
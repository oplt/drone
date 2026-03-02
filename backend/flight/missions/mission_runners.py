from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, List, Tuple
from backend.drone.models import Coordinate
from backend.drone.orchestrator import Orchestrator
import logging
import asyncio
from backend.services.photogrammetry.mission import make_photogrammetry_plan


logger = logging.getLogger(__name__)


@runtime_checkable
class Mission(Protocol):
    mission_type: str

    def get_waypoints(self) -> list[Coordinate]:
        ...

    async def execute(self, orch: "Orchestrator", alt: float) -> None:
        ...


@dataclass(frozen=True)
class BaseMission:
    mission_type: str

    def get_waypoints(self) -> list[Coordinate]:
        raise NotImplementedError

    async def execute(self, orch: "Orchestrator", alt: float) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class WaypointsMission(BaseMission):
    waypoints: list[Coordinate]

    def __init__(self, waypoints: list[Coordinate]):
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints (start & destination).")
        object.__setattr__(self, "mission_type", "waypoints")
        object.__setattr__(self, "waypoints", waypoints)

    def get_waypoints(self) -> list[Coordinate]:
        return self.waypoints


    async def fly_waypoints(self, orch: "Orchestrator", cruise_alt: float = 30.0, interpolate_steps: int = 6):

        waypoints = self.waypoints
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints (start & destination).")

        from backend.utils.geo import coord_from_home
        home_coord = coord_from_home(orch.drone.home_location)
        home_coord.alt = cruise_alt

        def _with_alt(w: Coordinate, default_alt: float) -> Coordinate:
            alt = getattr(w, "alt", None)
            if alt is None:
                return Coordinate(lat=w.lat, lon=w.lon, alt=default_alt)
            return w

        route: list[Coordinate] = (
                [home_coord]
                + [_with_alt(w, cruise_alt) for w in waypoints]
                + [home_coord]
        )

        start, dest = route[0], route[-2]  # home → ... → last waypoint → home
        orch._dest_coord = dest

        await asyncio.sleep(1.0)

        await asyncio.to_thread(orch.drone.arm_and_takeoff, cruise_alt)
        await orch.repo.add_event(orch._flight_id, "takeoff", {})

        # stitch segments; keep all anchors (home -> waypoints -> home)
        path: list[Coordinate] = []
        for a, b in zip(route, route[1:]):
            seg = (
                list(orch.maps.waypoints_between(a, b, steps=interpolate_steps))
                if interpolate_steps
                else [a, b]
            )
            if path and seg:
                seg = seg[1:]  # avoid duplicates at segment joints
            path.extend(seg)

        await asyncio.to_thread(orch.drone.follow_waypoints, path)
        await orch.repo.add_event(orch._flight_id, "reached_destination", {})

        # Wait for landing (RTL is already part of the path)
        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
        await orch.repo.add_event(orch._flight_id, "landed_home", {})
        await orch.repo.finish_flight(
            orch._flight_id,
            status="completed",
            note="Mission completed and returned home",
        )

    async def execute(self, orch: "Orchestrator", alt: float) -> None:
        logger.info(f"🚁 Starting mission type='waypoints' with {len(self.waypoints)} waypoint(s)")

        await orch.run_mission(
            self,
            alt=alt,
            flight_fn=lambda: self.fly_waypoints(orch, cruise_alt=alt),
        )


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
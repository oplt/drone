from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.db.models import FlightStatus
from backend.drone.models import Coordinate
from backend.drone.orchestrator import Orchestrator
from backend.flight.missions.terrain_follow import (
    apply_terrain_follow_to_path,
    resolve_home_amsl_m,
)



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


    async def fly_waypoints(
        self,
        orch: "Orchestrator",
        cruise_alt: float = 30.0,
        interpolate_steps: int = 6,
        terrain_mode: str = "REL_HOME",  # "REL_HOME" or "AMSL"
    ):

        waypoints = self.waypoints
        if len(waypoints) < 2:
            raise ValueError("Need at least 2 waypoints (start & destination).")

        from backend.utils.geo import coord_from_home
        home_coord = coord_from_home(orch.drone.home_location)

        # Treat cruise_alt as TARGET AGL (meters above ground)
        target_agl_m = float(cruise_alt)

        def _with_alt(w: Coordinate, default_alt: float) -> Coordinate:
            alt = getattr(w, "alt", None)
            if alt is None:
                return Coordinate(lat=w.lat, lon=w.lon, alt=default_alt)
            return w

        # Keep route anchors; alt here is not final anymore (we will overwrite per path point)
        route: list[Coordinate] = (
            [Coordinate(lat=home_coord.lat, lon=home_coord.lon, alt=target_agl_m)]
            + [_with_alt(w, target_agl_m) for w in waypoints]
            + [Coordinate(lat=home_coord.lat, lon=home_coord.lon, alt=target_agl_m)]
        )

        dest = route[-2]
        orch._dest_coord = dest

        if terrain_mode.upper() != "REL_HOME":
            logger.warning(
                "WaypointsMission terrain_mode=%s requested, but relative-home "
                "altitude is used by the active drone adapter.",
                terrain_mode,
            )

        home_amsl = await asyncio.to_thread(resolve_home_amsl_m, orch.drone)

        await asyncio.sleep(1.0)

        await asyncio.to_thread(orch.drone.arm_and_takeoff, target_agl_m)
        await orch.repo.add_event(orch._flight_id, "takeoff", {})

        requested_steps = max(0, int(interpolate_steps))
        path: list[Coordinate] = []
        for a, b in zip(route, route[1:]):
            seg = (
                list(orch.maps.waypoints_between(a, b, steps=requested_steps))
                if requested_steps > 0
                else [a, b]
            )
            if path and seg:
                prev = path[-1]
                first = seg[0]
                if (
                    abs(prev.lat - first.lat) <= 1e-9
                    and abs(prev.lon - first.lon) <= 1e-9
                    and abs(float(prev.alt) - float(first.alt)) <= 1e-6
                ):
                    seg = seg[1:]
            path.extend(seg)

        path = await apply_terrain_follow_to_path(
            maps_client=orch.maps,
            path=path,
            home_amsl_m=home_amsl,
            target_agl_m=target_agl_m,
        )

        await asyncio.to_thread(orch.drone.follow_waypoints, path)
        await orch.repo.add_event(orch._flight_id, "reached_destination", {})

        await asyncio.to_thread(orch.drone.land)
        await orch.repo.add_event(orch._flight_id, "landing_command_sent", {})

        await asyncio.to_thread(orch.drone.wait_until_disarmed, 900)
        await orch.repo.add_event(orch._flight_id, "landed_home", {})

        await orch.repo.finish_flight(
            orch._flight_id,
            status=FlightStatus.COMPLETED,
            note="Mission completed and returned home",
        )

    async def execute(self, orch: "Orchestrator", alt: float) -> None:
        logger.info(f"🚁 Starting mission type='waypoints' with {len(self.waypoints)} waypoint(s)")

        await orch.run_mission(
            self,
            alt=alt,
            flight_fn=lambda: self.fly_waypoints(orch, cruise_alt=alt),
        )

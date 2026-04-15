"""Controlled (manual-pilot) flight mission.

This mission type connects to the drone, runs preflight, starts telemetry, and
then holds an open session so the pilot can send real-time commands via the
manual-control API endpoint.  There is no autonomous waypoint following — the
pilot is in full control.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.db.models import FlightStatus
from backend.drone.models import Coordinate

if TYPE_CHECKING:
    from backend.drone.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

CONTROLLED_POLL_INTERVAL_S = 1.0


@dataclass
class ControlledFlightMission:
    mission_type: str = "controlled"
    cruise_alt: float = 30.0

    _abort_event: asyncio.Event = field(
        default_factory=asyncio.Event,
        init=False,
        repr=False,
        compare=False,
    )

    def get_waypoints(self) -> list[Coordinate]:
        return []

    def get_preflight_mission_data(self) -> dict[str, object]:
        return {
            "type": "controlled",
            "waypoints": [],
            "polygon": [],
            "speed": 0.0,
            "altitude_agl": float(self.cruise_alt),
            "control_mode": "manual_pilot",
        }

    async def execute(self, orch: Orchestrator, *, alt: float = 30.0) -> None:
        self.cruise_alt = float(alt)
        await orch.run_mission(
            self,
            alt=float(self.cruise_alt),
            flight_fn=lambda: self._hold_session(orch),
        )

    async def _hold_session(self, orch: Orchestrator) -> None:
        """Keep the mission session alive until abort or disconnect."""
        await self._add_event_safe(
            orch,
            "controlled_flight_session_started",
            {"cruise_alt": float(self.cruise_alt)},
        )

        try:
            while not self._abort_event.is_set():
                if getattr(orch.drone, "abort_requested", False):
                    break
                await asyncio.sleep(CONTROLLED_POLL_INTERVAL_S)
        except asyncio.CancelledError:
            pass

        await self._add_event_safe(orch, "controlled_flight_session_ended", {})
        await self._finish_flight_safe(
            orch,
            status=FlightStatus.COMPLETED,
            note="Controlled flight session ended",
        )

    def request_abort(self) -> None:
        self._abort_event.set()

    async def _finish_flight_safe(
        self,
        orch: Orchestrator,
        *,
        status: FlightStatus,
        note: str,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return
        try:
            await orch.repo.finish_flight(flight_id, status=status, note=note)
        except Exception:
            logger.exception(
                "ControlledFlightMission: failed to finish flight_id=%s", flight_id
            )

    async def _add_event_safe(
        self,
        orch: Orchestrator,
        event_type: str,
        data: dict | None = None,
    ) -> None:
        flight_id = getattr(orch, "_flight_id", None)
        if flight_id is None:
            return
        try:
            await orch.repo.add_event(flight_id, event_type, data or {})
        except Exception:
            logger.exception(
                "ControlledFlightMission: failed to persist event '%s' (flight_id=%s)",
                event_type,
                flight_id,
            )

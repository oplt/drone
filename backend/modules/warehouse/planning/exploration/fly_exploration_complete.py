from __future__ import annotations

from typing import TYPE_CHECKING

from backend.modules.missions.flight_models import FlightStatus

if TYPE_CHECKING:
    from backend.modules.vehicle_runtime.orchestrator import Orchestrator


class WarehouseExplorationFlyCompleteMixin:
    async def _fly_exploration_finalize(
        self,
        orch: Orchestrator,
        *,
        final_status: FlightStatus,
        final_note: str,
        mission_error: Exception | None,
    ) -> None:
        await self._finish_flight_safe(orch, status=final_status, note=final_note)

        event_type = (
            "indoor_mission_completed"
            if final_status == FlightStatus.COMPLETED
            else "indoor_mission_failed"
        )
        await self._add_event_safe(
            orch,
            event_type,
            {
                "state": self._state.value,
                "segments_completed": int(self._segments_completed),
                "docked": bool(self._docked_successfully),
                "flight_status": final_status.value,
                "error": str(mission_error) if mission_error is not None else None,
            },
        )

        if mission_error is not None:
            raise mission_error

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.modules.missions.api.mission_runtime_mappers import (
    db_status_for_runtime_state,
)
from backend.modules.missions.api.runtime_dto import MissionRuntimeRecord
from backend.modules.missions.application import mission_application
from backend.modules.missions.domain.state_machine import (
    MissionLifecycleState,
    is_terminal as is_terminal_state,
)
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.service.command_applicator import (
    _sync_runtime_flight_id_from_orchestrator,
)
from backend.modules.vehicle_runtime.vehicle_port import MissionAbortRequested
from backend.modules.warehouse.exceptions import WarehouseMissionFailure

logger = logging.getLogger(__name__)


async def set_runtime_state(
    runtime_id: str,
    *,
    state: MissionLifecycleState,
    error: str | None = None,
) -> None:
    await mission_application.set_state(runtime_id, state=state, error=error)


async def execute_mission(
    orch: Any,
    mission: Any,
    cruise_alt: float,
    mission_name: str,
    runtime_id: str,
) -> None:
    reconcile_db_flight_id: int | None = None
    reconcile_db_status: FlightStatus | None = None
    reconcile_note = ""
    terminal_state: MissionLifecycleState = "completed"
    terminal_error: str | None = None
    await set_runtime_state(runtime_id, state="airborne")
    try:
        await mission.execute(orch, alt=cruise_alt)
        logger.info("✅ Mission '%s' completed successfully", mission_name)
    except MissionAbortRequested as exc:
        terminal_state = "aborted"
        terminal_error = str(exc)
        logger.warning("🛑 Mission '%s' aborted: %s", mission_name, exc)
    except WarehouseMissionFailure as exc:
        terminal_error = str(exc.message or exc)
        if exc.stage == "capture" and exc.action == "complete":
            terminal_state = "completed"
            logger.warning(
                "⚠️ Mission '%s' flight completed with mapping failure: %s",
                mission_name,
                exc.message or exc,
            )
        else:
            terminal_state = "failed"
            logger.warning("🛑 Mission '%s' failed: %s", mission_name, exc)
    except asyncio.CancelledError:
        terminal_state = "failed"
        terminal_error = "Mission task cancelled unexpectedly"
        logger.exception(
            "Mission execution was cancelled",
            extra={"mission_id": runtime_id},
        )
    except Exception as exc:
        terminal_state = "failed"
        terminal_error = str(exc)
        logger.exception(
            "Mission execution failed",
            extra={"mission_id": runtime_id},
        )
    finally:
        db_row = await mission_application.finalize_execution(
            runtime_id,
            state=terminal_state,
            error=terminal_error,
        )
        try:
            from backend.modules.agriculture.service import agriculture_service

            await agriculture_service.reconcile_mission_terminal_state(
                mission_id=runtime_id,
                mission_state=terminal_state,
            )
        except Exception:
            logger.exception(
                "Failed reconciling agriculture lifecycle for mission %s",
                runtime_id,
            )
        if db_row is not None:
            runtime = MissionRuntimeRecord.from_db(db_row)
            await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
            if runtime.db_flight_id is not None and is_terminal_state(runtime.state):
                reconcile_db_flight_id = runtime.db_flight_id
                reconcile_db_status = db_status_for_runtime_state(runtime.state)
                reconcile_note = (
                    f"Mission {runtime.state}: {runtime.last_error}"
                    if runtime.last_error
                    else f"Mission {runtime.state}"
                )
                if runtime.state in {"completed", "failed", "aborted"}:
                    try:
                        from backend.modules.agents.hooks import (
                            schedule_postflight_for_mission_type,
                        )

                        schedule_postflight_for_mission_type(
                            runtime.mission_type,
                            mission_runtime_id=db_row.id,
                            client_flight_id=runtime_id,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to schedule postflight agents for %s",
                            runtime.mission_type,
                        )

        if reconcile_db_flight_id is not None and reconcile_db_status is not None:
            safe_note = (
                reconcile_note[:250] if reconcile_note else f"Mission {reconcile_db_status.value}"
            )
            try:
                await mission_application.finish_operational_flight(
                    orch.repo,
                    reconcile_db_flight_id,
                    status=reconcile_db_status,
                    note=safe_note,
                )
            except Exception:
                logger.exception(
                    "Failed reconciling terminal flight status to %s for db_flight_id=%s",
                    reconcile_db_status.value,
                    reconcile_db_flight_id,
                )
        if getattr(orch, "current_client_flight_id", None) == runtime_id:
            orch.current_client_flight_id = None
            orch.current_mission_name = None
            orch.current_mission_type = None
            orch.current_flight_environment = None
            orch.current_control_mode = None
            orch.current_mission_task_type = None
            orch.current_preflight_run_id = None

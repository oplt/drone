from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.modules.missions.api.mission_route_schemas import (
    MissionRuntimeOut,
    StateTransitionOut,
)
from backend.modules.missions.api.runtime_dto import (
    MissionCommandAuditOut,
    MissionCommandAuditRecord,
    MissionRuntimeRecord,
)
from backend.modules.missions.domain.state_machine import (
    TERMINAL_STATES as TERMINAL_MISSION_STATES,
    MissionLifecycleState,
    is_terminal as is_terminal_state,
)
from backend.modules.missions.flight_models import FlightStatus

__all__ = [
    "TERMINAL_MISSION_STATES",
    "audit_to_out",
    "build_state_timeline",
    "db_status_for_runtime_state",
    "runtime_to_out",
]


def db_status_for_runtime_state(state: MissionLifecycleState) -> FlightStatus:
    status_map = {
        "planned": FlightStatus.ACTIVE,
        "preflight": FlightStatus.ACTIVE,
        "queued": FlightStatus.ACTIVE,
        "arming": FlightStatus.ACTIVE,
        "airborne": FlightStatus.ACTIVE,
        "running": FlightStatus.ACTIVE,
        "paused": FlightStatus.PAUSED,
        "resumed": FlightStatus.ACTIVE,
        "aborting": FlightStatus.INTERRUPTED,
        "aborted": FlightStatus.INTERRUPTED,
        "completed": FlightStatus.COMPLETED,
        "failed": FlightStatus.FAILED,
    }
    return status_map.get(str(state), FlightStatus.FAILED)


def runtime_to_out(rec: MissionRuntimeRecord) -> MissionRuntimeOut:
    private_patrol_task_type = getattr(rec, "private_patrol_task_type", None)
    mission_task_type = getattr(rec, "mission_task_type", None)
    return MissionRuntimeOut(
        flight_id=rec.client_flight_id,
        mission_name=rec.mission_name,
        mission_type=rec.mission_type,
        mission_task_type=(private_patrol_task_type or mission_task_type or None),
        state=rec.state,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        preflight_run_id=rec.preflight_run_id,
        db_flight_id=str(rec.db_flight_id) if rec.db_flight_id is not None else None,
        last_error=rec.last_error,
    )


def audit_to_out(audit: MissionCommandAuditRecord) -> MissionCommandAuditOut:
    return MissionCommandAuditOut(
        command_id=audit.command_id,
        command=audit.command,
        idempotency_key=audit.idempotency_key,
        requested_by_user_id=audit.requested_by_user_id,
        requested_at=audit.requested_at,
        state_before=audit.state_before,
        state_after=audit.state_after,
        accepted=audit.accepted,
        message=audit.message,
        reason=audit.reason,
    )


def build_state_timeline(row: Any, commands: list) -> list[StateTransitionOut]:
    events: list[tuple[float, StateTransitionOut]] = []
    created_ts = row.created_at.timestamp() if isinstance(row.created_at, datetime) else 0.0
    events.append(
        (
            created_ts,
            StateTransitionOut(
                state=row.state if row.started_at is None and row.ended_at is None else "queued",
                entered_at=created_ts,
                trigger="mission_created",
            ),
        )
    )

    if row.started_at is not None:
        started_ts = (
            row.started_at.timestamp()
            if isinstance(row.started_at, datetime)
            else float(row.started_at)
        )
        events.append(
            (
                started_ts,
                StateTransitionOut(
                    state="airborne",
                    entered_at=started_ts,
                    trigger="execution_started",
                ),
            )
        )

    for cmd in commands:
        if not cmd.accepted:
            continue
        ts = (
            cmd.requested_at.timestamp()
            if isinstance(cmd.requested_at, datetime)
            else float(cmd.requested_at or 0)
        )
        events.append(
            (
                ts,
                StateTransitionOut(
                    state=cmd.state_after,
                    entered_at=ts,
                    trigger=f"command:{cmd.command}",
                    command_id=cmd.command_id,
                    command=cmd.command,
                    reason=cmd.reason,
                ),
            )
        )

    if row.ended_at is not None and is_terminal_state(row.state):
        ended_ts = (
            row.ended_at.timestamp() if isinstance(row.ended_at, datetime) else float(row.ended_at)
        )
        last_cmd_states = {event.state for _, event in events if event.command_id}
        if row.state not in last_cmd_states:
            events.append(
                (
                    ended_ts,
                    StateTransitionOut(
                        state=row.state,
                        entered_at=ended_ts,
                        trigger="execution_ended",
                        reason=row.failure_reason if row.failure_reason else None,
                    ),
                )
            )

    events.sort(key=lambda item: item[0])
    return [event for _, event in events]

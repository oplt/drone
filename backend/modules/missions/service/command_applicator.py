"""Apply operator mission commands with idempotency and lifecycle side effects."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from backend.core.events import (
    FlightEventEnvelopeV1,
    FlightEventPayloadV1,
    FlightEventSeverityV1,
    MissionLifecycleEnvelopeV1,
    MissionLifecyclePayloadV1,
    mission_context_from_runtime,
    next_runtime_sequence,
    utc_now,
)
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.missions.api.runtime_dto import (
    MissionCommand,
    MissionCommandOut,
    MissionRuntimeRecord,
)
from backend.modules.missions.application import mission_application
from backend.modules.missions.domain.state_machine import (
    allowed_command_target,
    is_terminal as sm_is_terminal,
)
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.domain.state_machine import MissionLifecycleState
from backend.observability.instruments import observed_span

logger = logging.getLogger(__name__)


def _is_terminal_state(state: str) -> bool:
    return sm_is_terminal(str(state).lower())


def _db_status_for_runtime_state(state: MissionLifecycleState) -> FlightStatus:
    mapping = {
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
    return mapping.get(str(state), FlightStatus.FAILED)


def _runtime_db_flight_id(runtime: MissionRuntimeRecord) -> int | None:
    try:
        return int(runtime.db_flight_id) if runtime.db_flight_id is not None else None
    except (TypeError, ValueError):
        return None


async def _sync_runtime_flight_id_from_orchestrator(
    runtime: MissionRuntimeRecord,
    orch: Any,
) -> None:
    if runtime.db_flight_id is not None:
        return
    raw = getattr(orch, "_flight_id", None)
    if raw is None:
        return
    try:
        fid = int(raw)
    except Exception:
        return
    runtime.db_flight_id = fid
    try:
        await mission_application.set_flight_id(runtime.client_flight_id, flight_id=fid)
    except Exception:
        logger.exception(
            "Failed persisting flight_id=%s for runtime %s",
            fid,
            runtime.client_flight_id,
        )


async def _persist_state_change_event(
    orch: Any,
    runtime: MissionRuntimeRecord,
    *,
    event_type: str,
    data: dict | BaseModel,
) -> None:
    if runtime.db_flight_id is None:
        return
    try:
        await orch.record_persisted_event(
            event_type,
            data=data,
            flight_id=int(runtime.db_flight_id),
            source="tasks.mission_control",
        )
    except Exception:
        logger.exception(
            "Failed to persist mission event %s for db_flight_id=%s",
            event_type,
            runtime.db_flight_id,
        )


async def apply_mission_command(
    *,
    orch: Any,
    runtime: MissionRuntimeRecord,
    command: MissionCommand,
    idempotency_key: str,
    requested_by_user_id: int,
    reason: str | None,
) -> MissionCommandOut:
    with observed_span(
        "mission.command.apply",
        mission_id=runtime.client_flight_id,
        mavlink_command=command,
    ):
        now = time.time()
        normalized_reason = (reason or "").strip() or None

        with observed_span("mission.command.idempotency"):
            existing = await mission_application.get_idempotency_result(
                runtime.client_flight_id, idempotency_key
            )
            if existing is not None:
                if str(existing.get("command")) != command:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency key already used for a different command.",
                    )
                return MissionCommandOut.model_validate(existing)

        await _sync_runtime_flight_id_from_orchestrator(runtime, orch)
        state_before = runtime.state
        state_after = state_before
        accepted = False
        message = ""

        target_state = allowed_command_target(state_before, command)
        if target_state is None:
            if _is_terminal_state(state_before):
                message = f"Mission already terminal ({state_before}); command ignored."
            else:
                message = f"Command '{command}' is invalid while mission is '{state_before}'."
        else:
            success = False
            with observed_span(
                "mission.command.drone",
                mission_id=runtime.client_flight_id,
                mavlink_command=command,
            ):
                if command == "pause":
                    success = await run_blocking(
                        orch.drone.pause_mission,
                        boundary="mavlink",
                        operation="pause_mission",
                        timeout_s=10.0,
                    )
                    message = (
                        "Mission paused."
                        if success
                        else "Pause command could not be applied on current drone connection."
                    )
                elif command == "resume":
                    success = await run_blocking(
                        orch.drone.resume_mission,
                        boundary="mavlink",
                        operation="resume_mission",
                        timeout_s=10.0,
                    )
                    message = (
                        "Mission resumed."
                        if success
                        else "Resume command could not be applied on current drone connection."
                    )
                elif command == "abort":
                    success = await run_blocking(
                        orch.drone.abort_mission,
                        boundary="mavlink",
                        operation="abort_mission",
                        timeout_s=10.0,
                    )
                    if not success:
                        logger.warning(
                            "Abort mode switch failed for mission %s; marking mission aborted anyway",
                            runtime.client_flight_id,
                        )
                    message = "Mission aborted by operator."
                elif command == "rth":
                    try:
                        await run_blocking(
                            orch.drone.set_mode,
                            "RTL",
                            boundary="mavlink",
                            operation="set_mode_rtl",
                            timeout_s=10.0,
                        )
                        success = True
                        message = "Return-to-home initiated."
                    except Exception as exc:
                        logger.warning(
                            "RTL mode switch failed for mission %s: %s",
                            runtime.client_flight_id,
                            exc,
                        )
                        message = f"RTH command failed: {exc}"
                elif command == "land":
                    try:
                        await run_blocking(
                            orch.drone.land,
                            boundary="mavlink",
                            operation="land",
                            timeout_s=10.0,
                        )
                        success = True
                        message = "Land-in-place initiated."
                    except Exception as exc:
                        logger.warning(
                            "Land command failed for mission %s: %s",
                            runtime.client_flight_id,
                            exc,
                        )
                        message = f"Land command failed: {exc}"
                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported command '{command}'")

            if success or command == "abort":
                accepted = True
                state_after = target_state

        command_id = f"cmd_{int(now)}_{uuid.uuid4().hex[:10]}"
        response_payload = {
            "flight_id": runtime.client_flight_id,
            "command_id": command_id,
            "command": command,
            "idempotency_key": idempotency_key,
            "state_before": state_before,
            "state_after": state_after,
            "accepted": accepted,
            "message": message,
            "requested_at": now,
        }

        audit_entry = {
            "command_id": command_id,
            "command": command,
            "idempotency_key": idempotency_key,
            "requested_by_user_id": int(requested_by_user_id),
            "requested_at": now,
            "state_before": state_before,
            "state_after": state_after,
            "accepted": accepted,
            "message": message,
            "reason": normalized_reason,
        }
        with observed_span(
            "mission.command.persist",
            mission_id=runtime.client_flight_id,
            mavlink_command=command,
        ):
            updated_row = await mission_application.apply_command(
                runtime.client_flight_id,
                new_state=state_after,
                audit_entry=audit_entry,
                idempotency_key=idempotency_key,
                idempotency_response=response_payload,
            )
        runtime.state = state_after

        try:
            requested_at_dt = datetime.fromtimestamp(now, tz=UTC)
            await mission_application.record_command(
                command_id=command_id,
                client_flight_id=runtime.client_flight_id,
                mission_runtime_id=updated_row.id if updated_row is not None else None,
                command=command,
                idempotency_key=idempotency_key,
                requested_by_user_id=int(requested_by_user_id),
                state_before=state_before,
                state_after=state_after,
                accepted=accepted,
                message=message,
                reason=normalized_reason,
                requested_at=requested_at_dt,
            )
        except Exception:
            logger.exception(
                "Failed persisting operator command record for %s / %s",
                runtime.client_flight_id,
                command_id,
            )

        if accepted:
            mission_context = mission_context_from_runtime(runtime)
            runtime_db_flight_id = _runtime_db_flight_id(runtime)
            flight_event_envelope = FlightEventEnvelopeV1(
                mission_runtime_id=runtime.client_flight_id,
                db_flight_id=runtime_db_flight_id,
                sequence=next_runtime_sequence(
                    runtime.client_flight_id,
                    "tasks.mission_control",
                ),
                emitted_at=utc_now(),
                source="tasks.mission_control",
                mission=mission_context,
                payload=FlightEventPayloadV1(
                    event_name="mission_command",
                    category="mission_control",
                    severity=FlightEventSeverityV1.INFO,
                    attributes={
                        "command_id": command_id,
                        "command": command,
                        "idempotency_key": idempotency_key,
                        "state_before": state_before,
                        "state_after": state_after,
                        "reason": normalized_reason,
                        "requested_by_user_id": int(requested_by_user_id),
                    },
                ),
            )
            await _persist_state_change_event(
                orch,
                runtime,
                event_type="mission_command",
                data=flight_event_envelope.payload,
            )
            lifecycle_envelope = MissionLifecycleEnvelopeV1(
                mission_runtime_id=runtime.client_flight_id,
                db_flight_id=runtime_db_flight_id,
                sequence=next_runtime_sequence(
                    runtime.client_flight_id,
                    "tasks.mission_control",
                ),
                emitted_at=utc_now(),
                source="tasks.mission_control",
                mission=mission_context,
                payload=MissionLifecyclePayloadV1(
                    state=state_after,
                    previous_state=state_before,
                    trigger=f"command:{command}",
                    reason=normalized_reason,
                    command_id=command_id,
                    requested_by_user_id=int(requested_by_user_id),
                ),
            )
            await _persist_state_change_event(
                orch,
                runtime,
                event_type="mission_state_changed",
                data=lifecycle_envelope.payload,
            )
            if runtime.db_flight_id is not None:
                if state_after in {"airborne", "running", "paused", "resumed"}:
                    try:
                        db_status = _db_status_for_runtime_state(state_after)
                        await mission_application.set_operational_flight_status(
                            orch.repo,
                            runtime.db_flight_id,
                            status=db_status,
                            note=message,
                        )
                    except Exception:
                        logger.exception(
                            "Failed updating flight status to %s for db_flight_id=%s",
                            db_status.value,
                            runtime.db_flight_id,
                        )
                elif state_after in {"aborting", "aborted"}:
                    try:
                        await mission_application.finish_operational_flight(
                            orch.repo,
                            runtime.db_flight_id,
                            status=FlightStatus.INTERRUPTED,
                            note=message,
                        )
                    except Exception:
                        logger.exception(
                            "Failed updating flight status to interrupted for db_flight_id=%s",
                            runtime.db_flight_id,
                        )

        return MissionCommandOut.model_validate(response_payload)

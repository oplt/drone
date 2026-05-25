"""Process-restart recovery for interrupted mission runtimes.

Called once at startup (after DB init, before accepting requests) to detect
any mission that was left in a non-terminal state by a prior crash or SIGKILL
and transition it to ``failed`` with an auditable reason.

Recovery also restores the orchestrator's in-memory context fields so that
any observability layer (WebSocket, metrics) reflects the correct mission
information during the brief recovery window.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from backend.modules.missions.command_repository import operator_command_repo
from backend.modules.missions.flight_models import FlightStatus
from backend.modules.missions.repository import mission_runtime_repo

logger = logging.getLogger(__name__)

RECOVERY_REASON = "process_restart: mission was interrupted by a backend restart or crash"


async def recover_interrupted_missions(orchestrator: Any) -> None:
    """Detect and close out any non-terminal mission left over from a prior run.

    Strategy
    --------
    * Query for the single active (non-terminal) mission runtime.
    * If none exists, return early — nothing to recover.
    * Restore the orchestrator's context fields from the DB record so that
      any in-flight observability (WebSocket, metrics) sees the right mission.
    * Mark the runtime as ``failed`` with reason ``process_restart``.
    * If the runtime has a linked DB flight record, close it as ``INTERRUPTED``.
    * Persist a synthetic ``operator_command`` audit row so the incident is
      traceable in the command history.
    """
    try:
        active_row = await mission_runtime_repo.get_active()
    except Exception:
        logger.exception("restart_recovery: failed to query active mission runtime")
        return

    if active_row is None:
        logger.debug("restart_recovery: no interrupted mission found")
        return

    logger.warning(
        "restart_recovery: found interrupted mission %r in state %r — marking failed",
        active_row.client_flight_id,
        active_row.state,
    )

    # Restore orchestrator context so observability reflects the correct mission.
    _restore_orchestrator_context(orchestrator, active_row)

    # Transition to failed.
    try:
        await mission_runtime_repo.set_state(
            active_row.client_flight_id,
            state="failed",
            error=RECOVERY_REASON,
        )
    except ValueError as exc:
        # Transition not valid per state machine (e.g. already terminal race).
        logger.warning("restart_recovery: state transition rejected: %s", exc)
        _clear_orchestrator_context(orchestrator, active_row.client_flight_id)
        return
    except Exception:
        logger.exception(
            "restart_recovery: failed to mark mission %r as failed",
            active_row.client_flight_id,
        )
        _clear_orchestrator_context(orchestrator, active_row.client_flight_id)
        return

    # Close the linked DB flight record if one exists.
    if active_row.flight_id is not None:
        try:
            await orchestrator.repo.finish_flight_if_in_progress(
                active_row.flight_id,
                status=FlightStatus.INTERRUPTED,
                note=f"Backend restart: mission {active_row.state} → failed",
            )
        except Exception:
            logger.exception(
                "restart_recovery: failed to close flight record %s",
                active_row.flight_id,
            )

    # Persist a synthetic operator command record for auditability.
    try:
        import time as _time
        import uuid

        now_dt = datetime.now(UTC)
        cmd_id = f"cmd_recovery_{int(_time.time())}_{uuid.uuid4().hex[:8]}"
        await operator_command_repo.create(
            command_id=cmd_id,
            client_flight_id=active_row.client_flight_id,
            mission_runtime_id=active_row.id,
            command="abort",
            idempotency_key=cmd_id,
            requested_by_user_id=None,
            state_before=active_row.state,
            state_after="failed",
            accepted=True,
            message=RECOVERY_REASON,
            reason="process_restart",
            requested_at=now_dt,
        )
    except Exception:
        logger.exception(
            "restart_recovery: failed to persist audit record for %r",
            active_row.client_flight_id,
        )

    _clear_orchestrator_context(orchestrator, active_row.client_flight_id)
    logger.info(
        "restart_recovery: mission %r recovered (was %r, now failed)",
        active_row.client_flight_id,
        active_row.state,
    )


def _restore_orchestrator_context(orchestrator: Any, row: Any) -> None:
    """Copy mission identity fields from the DB row onto the orchestrator."""
    orchestrator.current_client_flight_id = row.client_flight_id
    orchestrator.current_mission_name = row.mission_name
    orchestrator.current_mission_type = row.mission_type
    orchestrator.current_mission_task_type = row.mission_task_type
    orchestrator.current_preflight_run_id = row.preflight_run_uuid
    if row.flight_id is not None:
        orchestrator._flight_id = row.flight_id


def _clear_orchestrator_context(orchestrator: Any, client_flight_id: str) -> None:
    """Clear orchestrator context only if it still holds the recovered mission."""
    if getattr(orchestrator, "current_client_flight_id", None) == client_flight_id:
        orchestrator.current_client_flight_id = None
        orchestrator.current_mission_name = None
        orchestrator.current_mission_type = None
        orchestrator.current_mission_task_type = None
        orchestrator.current_preflight_run_id = None

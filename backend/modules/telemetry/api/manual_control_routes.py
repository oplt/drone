from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.core.logging import emit_app_log
from backend.modules.identity.dependencies import require_user
from backend.modules.identity.models import User
from backend.modules.telemetry.api.telemetry_route_schemas import ManualControlIn
from backend.modules.telemetry.api.telemetry_route_support import (
    track_background_task,
    velocity_for_manual_command,
)
from backend.modules.vehicle_runtime.factory import build_orchestrator as _build_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telemetry"])


@router.post("/manual-control")
async def send_manual_control(
    payload: ManualControlIn,
    user: User = Depends(require_user),
) -> dict[str, Any]:
    """Accept a pilot manual-control command and relay it to the drone.

    The frontend sends start/hold/stop phases per key press.  ``start`` and
    ``hold`` translate to velocity setpoints; ``stop`` sends a zero-velocity
    hold.  ``takeoff`` and ``land`` are handled as discrete one-shot commands.
    """
    orch = await _build_orchestrator()
    if getattr(orch, "async_drone", None) is None:
        raise HTTPException(status_code=503, detail="Drone not connected")

    cmd = payload.command
    phase = payload.phase
    logger.info(
        "Manual control command received command=%s phase=%s source=%s flight_id=%s",
        cmd,
        phase,
        payload.source,
        payload.flight_id,
    )

    if cmd == "takeoff":
        if phase == "stop":
            return {"status": "ignored", "command": cmd, "phase": phase}

        async def _bg_takeoff() -> None:
            try:
                await orch.async_drone.arm_and_takeoff(2.0)
                logger.info("Manual takeoff complete")
            except Exception:
                logger.critical(
                    "Manual takeoff failed",
                    extra={"source": "drone", "operation": "manual_takeoff"},
                    exc_info=True,
                )
                await emit_app_log(
                    level="critical",
                    source="drone",
                    message="Manual takeoff failed",
                    details={"command": cmd, "flight_id": payload.flight_id},
                    flight_id=payload.flight_id,
                )

        task = asyncio.create_task(_bg_takeoff())
        track_background_task(task)
        return {"status": "ok", "command": cmd, "detail": "takeoff initiated"}

    if cmd == "land":
        if phase == "stop":
            return {"status": "ignored", "command": cmd, "phase": phase}
        try:
            await orch.async_drone.land()
            await emit_app_log(
                level="info",
                source="drone",
                message="Manual landing command completed",
                details={"command": cmd, "flight_id": payload.flight_id},
                flight_id=payload.flight_id,
            )
            return {"status": "ok", "command": cmd}
        except Exception as exc:
            logger.critical(
                "Manual land failed",
                extra={"source": "drone", "operation": "manual_land"},
                exc_info=True,
            )
            await emit_app_log(
                level="critical",
                source="drone",
                message="Manual landing failed",
                details={"command": cmd, "flight_id": payload.flight_id, "error": str(exc)},
                flight_id=payload.flight_id,
            )
            raise HTTPException(status_code=503, detail="Landing command failed") from exc

    vx, vy, vz, yaw_rate = velocity_for_manual_command(cmd, phase)
    try:
        await orch.async_drone.set_mode("GUIDED")
        await orch.async_drone.send_velocity(vx, vy, vz, yaw_rate)
        logger.info(
            "Manual control velocity sent command=%s phase=%s "
            "vx=%.2f vy=%.2f vz=%.2f yaw_rate=%.2f",
            cmd,
            phase,
            vx,
            vy,
            vz,
            yaw_rate,
        )
        return {"status": "ok", "command": cmd, "phase": phase}
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="Active drone adapter does not support velocity commands",
        ) from None
    except (RuntimeError, AttributeError, OSError) as exc:
        raise HTTPException(
            status_code=503, detail="Drone link temporarily unavailable"
        ) from exc
    except Exception as exc:
        logger.exception("Velocity command failed")
        raise HTTPException(status_code=503, detail="Velocity command failed") from exc

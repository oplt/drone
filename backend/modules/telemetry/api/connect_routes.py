from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.core.logging import emit_app_log
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import require_user
from backend.modules.identity.models import User
from backend.modules.missions.flight_profile import (
    flight_profile_for_environment,
    flight_profile_for_mission_type,
)
from backend.modules.telemetry.api.telemetry_route_schemas import TelemetryConnectIn
from backend.modules.telemetry.api.telemetry_route_support import (
    connect_lock,
    expected_drone_connect_failure,
)
from backend.modules.vehicle_runtime.factory import build_orchestrator as _build_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telemetry"])


@router.post("/connect")
async def connect_drone_and_telemetry(
    payload: TelemetryConnectIn | None = None,
    user: User = Depends(require_user),
) -> dict[str, Any]:
    """Build orchestrator (connects drone) and start telemetry in one call."""
    profile = (
        flight_profile_for_environment(payload.flight_environment)
        if payload and payload.flight_environment is not None
        else flight_profile_for_mission_type(payload.mission_type if payload else None)
    )
    async with connect_lock:
        try:
            orch = await _build_orchestrator()
        except Exception as e:
            logger.error(
                "Drone orchestrator build failed during telemetry connect",
                extra={"source": "telemetry", "operation": "connect"},
                exc_info=True,
            )
            await emit_app_log(
                level="critical",
                source="drone",
                message="Drone connection could not be prepared",
                details={"operation": "telemetry_connect", "error": str(e)},
            )
            raise HTTPException(status_code=500, detail=f"Drone connection failed: {e!s}") from e

        drone = getattr(orch, "drone", None)
        if drone and not getattr(drone, "vehicle", None):
            try:
                await asyncio.to_thread(
                    drone.connect,
                    home_fallback_allowed=profile.allows_home_fallback,
                )
                logger.info(
                    "DroneKit vehicle connected via /telemetry/connect",
                    extra={
                        "source": "drone",
                        "operation": "connect",
                        "flight_environment": profile.environment.value,
                    },
                )
                await emit_app_log(
                    level="info",
                    source="drone",
                    message="Drone connected",
                    details={"operation": "telemetry_connect"},
                )
            except asyncio.CancelledError:
                logger.info("DroneKit vehicle connect cancelled during shutdown")
                raise
            except Exception as e:
                expected = expected_drone_connect_failure(e)
                log_fn = logger.warning if expected else logger.critical
                log_fn(
                    "DroneKit vehicle connect failed: %s",
                    e,
                    extra={"source": "mavlink", "operation": "connect"},
                    exc_info=not expected,
                )
                await emit_app_log(
                    level="warn" if expected else "critical",
                    source="mavlink",
                    message="Drone vehicle connection failed",
                    details={"operation": "telemetry_connect", "error": str(e)},
                )
                raise HTTPException(
                    status_code=503,
                    detail=f"Drone vehicle connection failed: {e!s}",
                ) from e

        if not telemetry_manager.runtime_snapshot()["running"]:
            try:
                await orch.start_live_telemetry()
            except asyncio.CancelledError:
                logger.info("Telemetry start cancelled during shutdown")
                raise
            except Exception as e:
                logger.error(
                    "Failed to start telemetry",
                    extra={"source": "telemetry", "operation": "start"},
                    exc_info=True,
                )
                await emit_app_log(
                    level="error",
                    source="telemetry",
                    message="Telemetry stream failed to start",
                    details={"operation": "telemetry_connect", "error": str(e)},
                )
                raise HTTPException(status_code=500, detail=f"Telemetry start failed: {e!s}") from e

        return {
            "status": "connected",
            "drone": drone is not None and getattr(drone, "vehicle", None) is not None,
            "telemetry_running": telemetry_manager.runtime_snapshot()["running"],
            "flight_environment": profile.environment.value,
        }

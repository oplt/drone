from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_mission_exec, require_org_user
from backend.modules.warehouse.exceptions import WarehouseFlightNotReadyError
from backend.modules.warehouse.service.flight_service import (
    WarehouseFlightMissionContext,
    assert_ready_for_warehouse_flight_start,
    evaluate_warehouse_flight_readiness,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flight", tags=["warehouse-flight"])


class WarehouseFlightSubsystemOut(BaseModel):
    status: str
    message: str
    last_seen_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    stable_for_ms: int | None = None
    required_stable_ms: int | None = None
    costmap_age_ms: int | None = None


class WarehouseFlightReadinessOut(BaseModel):
    ready_to_arm: bool
    ready_to_takeoff: bool
    ready_for_autonomy: bool
    overall_status: str
    current_state: str
    subsystems: dict[str, WarehouseFlightSubsystemOut]
    blocking_reasons: list[str]
    updated_at: datetime
    slam_stable_for_ms: int = 0
    slam_required_stable_ms: int = 0
    perception_stable_for_ms: int = 0
    perception_required_stable_ms: int = 0


class WarehouseFlightStartIn(BaseModel):
    warehouse_map_id: int = Field(..., ge=1)
    mission_name: str = Field(default="Warehouse Scan", min_length=1, max_length=120)
    reference_mapping_job_id: int | None = Field(default=None, ge=1)
    sensor_rig_id: int | None = Field(default=None, ge=1)
    dock_id: int | None = Field(default=None, ge=1)
    work_speed_mps: float | None = Field(default=None, gt=0.0, le=5.0)
    cruise_alt: float | None = Field(default=None, gt=0.2, le=20.0)


class WarehouseFlightStartOut(BaseModel):
    accepted: bool
    reason: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    readiness: WarehouseFlightReadinessOut | None = None
    launch: dict[str, Any] | None = None


class WarehouseFlightCommandIn(BaseModel):
    command: Literal["pause", "resume", "abort", "land", "rth"]


class WarehouseFlightCommandOut(BaseModel):
    accepted: bool
    message: str


def _subsystem_out(key: str, payload: dict[str, Any]) -> WarehouseFlightSubsystemOut:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    stable_for_ms = details.get("stable_for_ms")
    if key == "slam" and isinstance(stable_for_ms, int):
        return WarehouseFlightSubsystemOut(
            status=str(payload.get("status") or "UNKNOWN"),
            message=str(payload.get("message") or ""),
            last_seen_ms=payload.get("last_seen_ms"),
            details=details,
            stable_for_ms=stable_for_ms,
            required_stable_ms=details.get("required_stable_ms"),
        )
    costmap_age_ms = details.get("costmap_age_ms")
    if key == "nvblox" and isinstance(costmap_age_ms, int):
        return WarehouseFlightSubsystemOut(
            status=str(payload.get("status") or "UNKNOWN"),
            message=str(payload.get("message") or ""),
            last_seen_ms=payload.get("last_seen_ms"),
            details=details,
            costmap_age_ms=costmap_age_ms,
        )
    return WarehouseFlightSubsystemOut(
        status=str(payload.get("status") or "UNKNOWN"),
        message=str(payload.get("message") or ""),
        last_seen_ms=payload.get("last_seen_ms"),
        details=details,
    )


def _readiness_out(payload: dict[str, Any]) -> WarehouseFlightReadinessOut:
    subsystems_raw = payload.get("subsystems") if isinstance(payload.get("subsystems"), dict) else {}
    subsystems = {
        str(key): _subsystem_out(str(key), value if isinstance(value, dict) else {})
        for key, value in subsystems_raw.items()
    }
    updated_at_raw = payload.get("updated_at")
    if isinstance(updated_at_raw, str):
        updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
    else:
        updated_at = datetime.utcnow()
    return WarehouseFlightReadinessOut(
        ready_to_arm=bool(payload.get("ready_to_arm")),
        ready_to_takeoff=bool(payload.get("ready_to_takeoff")),
        ready_for_autonomy=bool(payload.get("ready_for_autonomy")),
        overall_status=str(payload.get("overall_status") or "UNKNOWN"),
        current_state=str(payload.get("current_state") or "IDLE"),
        subsystems=subsystems,
        blocking_reasons=list(payload.get("blocking_reasons") or []),
        updated_at=updated_at,
        slam_stable_for_ms=int(payload.get("slam_stable_for_ms") or 0),
        slam_required_stable_ms=int(payload.get("slam_required_stable_ms") or 0),
        perception_stable_for_ms=int(payload.get("perception_stable_for_ms") or 0),
        perception_required_stable_ms=int(payload.get("perception_required_stable_ms") or 0),
    )


@router.get("/readiness", response_model=WarehouseFlightReadinessOut)
async def get_warehouse_flight_readiness(
    mission_loaded: bool = False,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseFlightReadinessOut:
    snapshot = await evaluate_warehouse_flight_readiness(
        mission=WarehouseFlightMissionContext(loaded=mission_loaded, valid=mission_loaded),
    )
    return _readiness_out(snapshot.to_dict())


@router.post("/start", response_model=WarehouseFlightStartOut)
async def start_warehouse_flight(
    payload: WarehouseFlightStartIn,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseFlightStartOut:
    mission_ctx = WarehouseFlightMissionContext(
        loaded=True,
        valid=payload.warehouse_map_id > 0 and payload.sensor_rig_id is not None,
        speed_mps=payload.work_speed_mps,
        altitude_m=payload.cruise_alt,
    )
    try:
        snapshot = await assert_ready_for_warehouse_flight_start(mission=mission_ctx)
    except WarehouseFlightNotReadyError as exc:
        return WarehouseFlightStartOut(
            accepted=False,
            reason="WAREHOUSE_FLIGHT_NOT_READY",
            blocking_reasons=exc.blocking_reasons,
            readiness=_readiness_out(exc.readiness),
        )

    from backend.modules.warehouse.api import WarehouseScanStartIn, start_warehouse_scan

    launch = await start_warehouse_scan(
        WarehouseScanStartIn(
            warehouse_map_id=payload.warehouse_map_id,
            mission_name=payload.mission_name,
            reference_mapping_job_id=payload.reference_mapping_job_id,
            sensor_rig_id=payload.sensor_rig_id,
            dock_id=payload.dock_id,
            cruise_alt=payload.cruise_alt,
            work_speed_mps=payload.work_speed_mps,
        ),
        db=db,
        org_user=org_user,
    )
    from backend.modules.warehouse.service.flight_watchdog import get_warehouse_flight_watchdog

    get_warehouse_flight_watchdog().start()
    return WarehouseFlightStartOut(
        accepted=True,
        readiness=_readiness_out(snapshot.to_dict()),
        launch=launch.model_dump(mode="json"),
    )


@router.post("/command", response_model=WarehouseFlightCommandOut)
async def warehouse_flight_command(
    payload: WarehouseFlightCommandIn,
    _org_user: OrgUser = Depends(require_mission_exec),
) -> WarehouseFlightCommandOut:
    import asyncio

    from backend.modules.missions.api.routes import get_orchestrator

    orch = await get_orchestrator()
    command = payload.command
    success = False
    if command == "pause":
        success = await asyncio.to_thread(orch.drone.pause_mission)
        message = "Mission paused." if success else "Pause command failed."
    elif command == "resume":
        success = await asyncio.to_thread(orch.drone.resume_mission)
        message = "Mission resumed." if success else "Resume command failed."
    elif command == "abort":
        success = await asyncio.to_thread(orch.drone.abort_mission)
        message = "Mission aborted."
        success = True
    elif command == "land":
        success = await asyncio.to_thread(orch.drone.set_mode, "LAND")
        message = "Land command sent." if success else "Land command failed."
    elif command == "rth":
        success = await asyncio.to_thread(orch.drone.set_mode, "RTL")
        message = "Return-to-home initiated." if success else "RTH command failed."
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported command: {command}")

    if command in {"abort", "land"}:
        from backend.modules.warehouse.service.flight_watchdog import get_warehouse_flight_watchdog

        get_warehouse_flight_watchdog().stop()
    return WarehouseFlightCommandOut(accepted=success, message=message)

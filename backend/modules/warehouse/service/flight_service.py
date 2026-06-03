from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from backend.modules.vehicle_runtime.types import Telemetry
from backend.modules.warehouse.exceptions import WarehouseFlightNotReadyError
from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_readiness import (
    WarehouseFlightReadiness,
    evaluate_subsystems_from_components,
    get_slam_stability_tracker,
)
from backend.modules.warehouse.service.flight_state_machine import (
    WarehouseFlightState,
    get_warehouse_flight_state_machine,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WarehouseFlightMissionContext:
    loaded: bool = False
    valid: bool = False
    speed_mps: float | None = None
    altitude_m: float | None = None


@dataclass(frozen=True)
class WarehouseFlightReadinessSnapshot:
    readiness: WarehouseFlightReadiness
    current_state: WarehouseFlightState

    def to_dict(self) -> dict[str, Any]:
        payload = self.readiness.to_dict()
        payload["current_state"] = self.current_state.value
        return payload


async def _fetch_autopilot_telemetry() -> Telemetry | None:
    try:
        from backend.modules.missions.api.routes import get_orchestrator

        orch = await get_orchestrator()
        return await asyncio.to_thread(orch.drone.get_telemetry)
    except Exception as exc:
        logger.debug("Autopilot telemetry unavailable for warehouse flight readiness: %s", exc)
        return None


async def _mapping_stack_running() -> bool:
    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        warehouse_mapping_stack_status,
    )

    status = await warehouse_mapping_stack_status()
    return bool(status.running)


async def evaluate_warehouse_flight_readiness(
    *,
    deep: bool = True,
    force: bool = True,
    mission: WarehouseFlightMissionContext | None = None,
    in_flight: bool = False,
    user_armed: bool = False,
    autonomous: bool = False,
    mapping_stack_running: bool | None = None,
) -> WarehouseFlightReadinessSnapshot:
    config = WarehouseFlightConfig.from_env()
    if deep or force:
        from backend.modules.warehouse.service.warehouse_preflight import (
            fetch_warehouse_perception_status,
        )

        status = await fetch_warehouse_perception_status(deep=deep, force=force)
    else:
        from backend.modules.warehouse.service.idle_health import (
            fetch_idle_warehouse_perception_status,
        )

        status = await fetch_idle_warehouse_perception_status()
    components = status.components if isinstance(status.components, dict) else {}
    telemetry = await _fetch_autopilot_telemetry()
    stack_running = (
        mapping_stack_running
        if mapping_stack_running is not None
        else await _mapping_stack_running()
    )

    mission_ctx = mission or WarehouseFlightMissionContext()
    readiness = evaluate_subsystems_from_components(
        status=status,
        components=components,
        telemetry=telemetry,
        config=config,
        mission_loaded=mission_ctx.loaded,
        mission_valid=mission_ctx.valid,
        speed_mps=mission_ctx.speed_mps,
        altitude_m=mission_ctx.altitude_m,
        stability_tracker=get_slam_stability_tracker(),
        mapping_stack_running=stack_running,
    )

    state_machine = get_warehouse_flight_state_machine()
    current_state = state_machine.sync_from_readiness(
        readiness,
        in_flight=in_flight,
        user_armed=user_armed,
        autonomous=autonomous,
    )
    return WarehouseFlightReadinessSnapshot(readiness=readiness, current_state=current_state)


async def assert_ready_for_core_takeoff(
    *,
    mission: WarehouseFlightMissionContext,
    wait_for_stability: bool = True,
) -> WarehouseFlightReadinessSnapshot:
    """Gate on bridge, sensors, SLAM, and perception stability — not nvblox."""
    if wait_for_stability:
        from backend.modules.warehouse.service.perception_stable_preflight import (
            ensure_warehouse_perception_stable,
        )

        snapshot = await ensure_warehouse_perception_stable(mission=mission)
    else:
        snapshot = await evaluate_warehouse_flight_readiness(mission=mission, force=True)

    if not snapshot.readiness.ready_to_takeoff:
        logger.warning(
            "Warehouse core takeoff readiness refused blocking=%s overall=%s",
            snapshot.readiness.blocking_reasons,
            snapshot.readiness.overall_status.value,
        )
        raise WarehouseFlightNotReadyError(
            blocking_reasons=snapshot.readiness.blocking_reasons,
            readiness=snapshot.to_dict(),
        )
    return snapshot


def _mission_planner_blocking_reasons(
    mission: WarehouseFlightMissionContext,
    *,
    config: WarehouseFlightConfig | None = None,
) -> list[str]:
    """Fast mission constraint checks before ROS/nvblox bootstrap waits."""
    cfg = config or WarehouseFlightConfig.from_env()
    reasons: list[str] = []
    if not mission.loaded:
        reasons.append("Mission not loaded")
    if not mission.valid:
        reasons.append("Mission path or waypoints invalid")
    if mission.speed_mps is not None and mission.speed_mps > cfg.max_indoor_speed_mps:
        reasons.append(
            f"Speed above indoor limit ({mission.speed_mps:.2f} m/s > {cfg.max_indoor_speed_mps:.2f} m/s)"
        )
    if mission.altitude_m is not None and mission.altitude_m > cfg.max_indoor_altitude_m:
        reasons.append(
            f"Altitude above indoor limit ({mission.altitude_m:.2f} m > {cfg.max_indoor_altitude_m:.2f} m)"
        )
    return reasons


async def assert_ready_for_warehouse_flight_start(
    *,
    mission: WarehouseFlightMissionContext,
    wait_for_stability: bool = True,
) -> WarehouseFlightReadinessSnapshot:
    planner_blockers = _mission_planner_blocking_reasons(mission)
    if planner_blockers:
        raise WarehouseFlightNotReadyError(
            blocking_reasons=planner_blockers,
            readiness={},
        )

    snapshot = await assert_ready_for_core_takeoff(
        mission=mission,
        wait_for_stability=wait_for_stability,
    )

    from backend.modules.warehouse.service.mapping_stack_lifecycle import (
        prepare_warehouse_scan_ros,
    )
    from backend.modules.warehouse.service.perception_stable_preflight import (
        ensure_warehouse_perception_stable,
    )

    stack_status, mapping_readiness, _takeoff_ready = await prepare_warehouse_scan_ros(
        require_nvblox=True,
    )
    if not stack_status.running:
        detail = stack_status.last_error or "mapping stack failed to start"
        raise WarehouseFlightNotReadyError(
            blocking_reasons=[f"nvblox: {detail}"],
            readiness=snapshot.to_dict(),
        )
    if not mapping_readiness.nvblox_ready:
        detail = (
            mapping_readiness.detail
            or "nvblox outputs not publishing after mapping stack start"
        )
        missing = mapping_readiness.missing_nvblox
        if missing and "missing outputs" not in detail:
            detail = f"{detail}; missing outputs: {', '.join(missing)}"
        raise WarehouseFlightNotReadyError(
            blocking_reasons=[f"nvblox: {detail}"],
            readiness=snapshot.to_dict(),
        )

    snapshot = await ensure_warehouse_perception_stable(
        mission=mission,
        mapping_stack_running=True,
        timeout_s=float(os.getenv("WAREHOUSE_FLIGHT_POST_NVBLOX_STABLE_S", "45")),
    )
    if not snapshot.readiness.ready_for_autonomy:
        logger.warning(
            "Warehouse flight start refused after nvblox bootstrap blocking=%s overall=%s",
            snapshot.readiness.blocking_reasons,
            snapshot.readiness.overall_status.value,
        )
        raise WarehouseFlightNotReadyError(
            blocking_reasons=snapshot.readiness.blocking_reasons,
            readiness=snapshot.to_dict(),
        )
    logger.info(
        "Warehouse flight start readiness passed state=%s",
        snapshot.current_state.value,
    )
    return snapshot

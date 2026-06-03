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


async def _bootstrap_telemetry_for_flight() -> list[str]:
    """Mirror POST /telemetry/connect so flight start does not fail on a cold runtime."""
    import asyncio

    from backend.infrastructure.messaging.websocket_publisher import telemetry_manager

    if telemetry_manager.runtime_snapshot().get("running"):
        return []

    notes: list[str] = []
    try:
        from backend.modules.missions.api.routes import get_orchestrator

        orch = await get_orchestrator()
    except Exception as exc:
        logger.warning("Warehouse flight telemetry bootstrap: orchestrator unavailable: %s", exc)
        return [f"Mission orchestrator unavailable: {exc}"]

    drone = getattr(orch, "drone", None)
    if drone is not None and not getattr(drone, "vehicle", None):
        try:
            await asyncio.to_thread(drone.connect)
            logger.info("Warehouse flight gate: DroneKit session connected")
        except Exception as exc:
            logger.warning("Warehouse flight gate: DroneKit connect failed: %s", exc)
            notes.append(
                f"Autopilot connection failed: {exc}. "
                "Start SITL/MAVProxy (e.g. udp:127.0.0.1:14550) and use Connect Drone."
            )

    if not telemetry_manager.runtime_snapshot().get("running"):
        try:
            await orch.start_live_telemetry()
            logger.info("Warehouse flight gate: live telemetry ingest started")
        except Exception as exc:
            logger.warning("Warehouse flight gate: telemetry start failed: %s", exc)
            notes.append(f"Telemetry start failed: {exc}")
    return notes


async def _mavlink_flight_start_blockers() -> list[str]:
    """Warehouse missions move the vehicle via MAVLink; ROS odom alone is insufficient."""
    config = WarehouseFlightConfig.from_env()
    if not config.require_mavlink_for_flight:
        return []

    import time

    from backend.infrastructure.messaging.websocket_publisher import telemetry_manager

    reasons: list[str] = await _bootstrap_telemetry_for_flight()
    runtime = telemetry_manager.runtime_snapshot()
    if not runtime.get("running"):
        reasons.append(
            "Telemetry runtime is not running. Click Connect Drone in the app "
            "(or POST /api/telemetry/connect), then retry warehouse flight."
        )
    if not runtime.get("source_connected"):
        reasons.append(
            "MAVLink not connected. Connect drone/SITL telemetry before flight "
            "(Gazebo: ArduPilot SITL or MAVProxy on udp:127.0.0.1:14550)"
        )
    last_update = float(runtime.get("last_update") or 0.0)
    if last_update > 0.0 and (time.time() - last_update) > 15.0:
        reasons.append(
            f"MAVLink telemetry stale ({time.time() - last_update:.0f}s old)"
        )
    try:
        from backend.modules.missions.api.routes import get_orchestrator

        orch = await get_orchestrator()
        if getattr(orch.drone, "vehicle", None) is None:
            reasons.append(
                "Autopilot session not initialized. Use Connect Drone before warehouse flight."
            )
    except Exception as exc:
        logger.debug("Orchestrator unavailable for MAVLink flight gate: %s", exc)
        if not any("orchestrator" in item.lower() for item in reasons):
            reasons.append("Mission orchestrator unavailable for MAVLink flight")
    # De-dupe while preserving order
    deduped: list[str] = []
    seen: set[str] = set()
    for item in reasons:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


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
        parallel_takeoff=False,
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
        actions = [
            "Ensure bridge stack is running (not only Gazebo: need ros2 topic hz on /warehouse/front/rgbd/image)",
            "Restart mapping: bash scripts/start_warehouse_nvblox.sh (ROS_DOMAIN_ID=42)",
            f"Then verify: ros2 topic hz /nvblox_node/static_esdf_pointcloud",
        ]
        raise WarehouseFlightNotReadyError(
            blocking_reasons=[f"nvblox: {detail}", *actions[:2]],
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

    mavlink_blockers = await _mavlink_flight_start_blockers()
    if mavlink_blockers:
        logger.warning(
            "Warehouse flight start refused: MAVLink required blocking=%s",
            mavlink_blockers,
        )
        raise WarehouseFlightNotReadyError(
            blocking_reasons=mavlink_blockers,
            readiness=snapshot.to_dict(),
        )

    logger.info(
        "Warehouse flight start readiness passed state=%s",
        snapshot.current_state.value,
    )
    return snapshot

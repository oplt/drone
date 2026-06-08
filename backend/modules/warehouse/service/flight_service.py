from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.modules.warehouse.exceptions import WarehouseFlightNotReadyError
from backend.modules.warehouse.service.readiness_result import (
    readiness_from_perception_status_strict,
)


@dataclass(frozen=True)
class WarehouseFlightMissionContext:
    loaded: bool = False
    valid: bool = False
    speed_mps: float | None = None
    altitude_m: float | None = None


@dataclass(frozen=True)
class WarehouseFlightReadinessSnapshot:
    ready_to_arm: bool
    ready_to_takeoff: bool
    ready_for_autonomy: bool
    overall_status: str
    current_state: str
    subsystems: dict[str, dict[str, Any]]
    blocking_reasons: list[str]
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    slam_stable_for_ms: int = 0
    slam_required_stable_ms: int = 0
    perception_stable_for_ms: int = 0
    perception_required_stable_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready_to_arm": self.ready_to_arm,
            "ready_to_takeoff": self.ready_to_takeoff,
            "ready_for_autonomy": self.ready_for_autonomy,
            "overall_status": self.overall_status,
            "current_state": self.current_state,
            "subsystems": self.subsystems,
            "blocking_reasons": self.blocking_reasons,
            "updated_at": self.updated_at.isoformat(),
            "slam_stable_for_ms": self.slam_stable_for_ms,
            "slam_required_stable_ms": self.slam_required_stable_ms,
            "perception_stable_for_ms": self.perception_stable_for_ms,
            "perception_required_stable_ms": self.perception_required_stable_ms,
        }


async def evaluate_warehouse_flight_readiness(
    *,
    deep: bool = False,
    force: bool = False,
    mission: WarehouseFlightMissionContext | None = None,
) -> WarehouseFlightReadinessSnapshot:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    mission = mission or WarehouseFlightMissionContext()
    status = await build_warehouse_perception_port().status(deep=deep, force=force)
    readiness = readiness_from_perception_status_strict(status)
    components = status.components if isinstance(status.components, dict) else {}
    stable_for_ms = int(
        components.get("perception_stable_for_ms") or components.get("stable_for_ms") or 0
    )
    required_stable_ms = int(
        components.get("perception_required_stable_ms")
        or components.get("required_stable_ms")
        or 8000
    )
    stability_ok = stable_for_ms >= required_stable_ms

    blockers: list[str] = []
    if not mission.loaded:
        blockers.append("Warehouse mission is not loaded.")
    elif not mission.valid:
        blockers.append("Warehouse mission is missing a valid map or calibrated sensor rig.")
    if not readiness.bridge_reachable:
        blockers.append(readiness.detail or "Warehouse ROS bridge is not reachable.")
    if not readiness.can_localize:
        blockers.append("Warehouse local odometry / SLAM is not ready.")
    if not readiness.nvblox_ready:
        blockers.append("Nvblox ESDF/costmap is not ready.")
    if not stability_ok:
        blockers.append("Perception stability window has not passed.")

    ready_to_takeoff = not blockers
    subsystems = {
        "bridge": {
            "status": "OK" if readiness.bridge_reachable else "BLOCKED",
            "message": readiness.detail
            or ("Bridge reachable" if readiness.bridge_reachable else "Bridge not reachable"),
            "details": {"configured": status.configured, "bridge_url": status.bridge_url},
        },
        "slam": {
            "status": "OK" if readiness.can_localize else "BLOCKED",
            "message": (
                "Local odometry / SLAM ready"
                if readiness.can_localize
                else "Local odometry / SLAM unavailable"
            ),
            "details": {"stable_for_ms": stable_for_ms, "required_stable_ms": required_stable_ms},
        },
        "nvblox": {
            "status": "OK" if readiness.nvblox_ready else "WAITING",
            "message": (
                "Nvblox is publishing map data"
                if readiness.nvblox_ready
                else "Nvblox has not published a ready map signal"
            ),
            "details": {"costmap_age_ms": components.get("costmap_age_ms")},
        },
    }
    return WarehouseFlightReadinessSnapshot(
        ready_to_arm=readiness.bridge_reachable and readiness.can_localize,
        ready_to_takeoff=ready_to_takeoff,
        ready_for_autonomy=ready_to_takeoff,
        overall_status="READY" if ready_to_takeoff else "BLOCKED",
        current_state="READY" if ready_to_takeoff else "WAITING",
        subsystems=subsystems,
        blocking_reasons=blockers,
        slam_stable_for_ms=stable_for_ms,
        slam_required_stable_ms=required_stable_ms,
        perception_stable_for_ms=stable_for_ms,
        perception_required_stable_ms=required_stable_ms,
    )


async def assert_ready_for_warehouse_flight_start(
    *,
    mission: WarehouseFlightMissionContext,
) -> WarehouseFlightReadinessSnapshot:
    snapshot = await evaluate_warehouse_flight_readiness(
        deep=True,
        force=True,
        mission=mission,
    )
    if not snapshot.ready_to_takeoff:
        raise WarehouseFlightNotReadyError(
            blocking_reasons=snapshot.blocking_reasons,
            readiness=snapshot.to_dict(),
        )
    return snapshot

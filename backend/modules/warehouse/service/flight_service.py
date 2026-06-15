from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.modules.warehouse.exceptions import WarehouseFlightNotReadyError
from backend.modules.warehouse.service.readiness_result import (
    readiness_from_perception_status_strict,
)

logger = logging.getLogger(__name__)
_DEFAULT_READINESS_TIMEOUT_S = 10.0


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _settings_readiness_timeout_s() -> float:
    try:
        from backend.core.config.runtime import settings

        raw = getattr(settings, "warehouse_flight_readiness_timeout_s", None)
    except Exception:
        raw = None
    try:
        return max(0.5, float(raw if raw is not None else _DEFAULT_READINESS_TIMEOUT_S))
    except (TypeError, ValueError):
        return _DEFAULT_READINESS_TIMEOUT_S


def _blocked_snapshot(*, reason: str, detail: str | None = None) -> WarehouseFlightReadinessSnapshot:
    blockers = [reason]
    return WarehouseFlightReadinessSnapshot(
        ready_to_arm=False,
        ready_to_takeoff=False,
        ready_for_autonomy=False,
        overall_status="BLOCKED",
        current_state="WAITING",
        subsystems={
            "bridge": {
                "status": "BLOCKED",
                "message": detail or reason,
                "details": {"configured": False, "bridge_url": None},
            },
            "slam": {
                "status": "BLOCKED",
                "message": "Local odometry / SLAM status is unavailable.",
                "details": {"stable_for_ms": 0, "required_stable_ms": 0},
            },
            "nvblox": {
                "status": "WAITING",
                "message": "Nvblox status is unavailable.",
                "details": {"costmap_age_ms": None},
            },
        },
        blocking_reasons=blockers,
    )


async def evaluate_warehouse_flight_readiness(
    *,
    deep: bool = False,
    force: bool = False,
    mission: WarehouseFlightMissionContext | None = None,
) -> WarehouseFlightReadinessSnapshot:
    from backend.infrastructure.warehouse.perception import build_warehouse_perception_port

    mission = mission or WarehouseFlightMissionContext()
    port = build_warehouse_perception_port()
    timeout_s = _settings_readiness_timeout_s()

    try:
        status = await asyncio.wait_for(
            port.status(deep=deep, force=force),
            timeout=timeout_s,
        )
    except TimeoutError:
        logger.warning(
            "warehouse_flight_readiness_timeout",
            extra={"timeout_s": timeout_s, "deep": deep, "force": force},
        )
        return _blocked_snapshot(
            reason="Warehouse perception status timed out.",
            detail=f"Perception status did not respond within {timeout_s:.1f}s.",
        )
    except Exception as exc:
        logger.exception("warehouse_flight_readiness_status_failed")
        return _blocked_snapshot(
            reason="Warehouse perception status failed.",
            detail=str(exc),
        )

    readiness = readiness_from_perception_status_strict(status)
    components = status.components if isinstance(getattr(status, "components", None), dict) else {}

    perception_stable_for_ms = _safe_int(
        components.get("perception_stable_for_ms", components.get("stable_for_ms")),
        0,
    )
    perception_required_stable_ms = _safe_int(
        components.get("perception_required_stable_ms", components.get("required_stable_ms")),
        8000,
    )
    slam_stable_for_ms = _safe_int(
        components.get("slam_stable_for_ms", perception_stable_for_ms),
        perception_stable_for_ms,
    )
    slam_required_stable_ms = _safe_int(
        components.get("slam_required_stable_ms", perception_required_stable_ms),
        perception_required_stable_ms,
    )

    perception_stability_ok = perception_stable_for_ms >= perception_required_stable_ms
    slam_stability_ok = slam_stable_for_ms >= slam_required_stable_ms

    blockers: list[str] = []
    if not mission.loaded:
        blockers.append("Warehouse mission is not loaded.")
    elif not mission.valid:
        blockers.append("Warehouse mission is missing a valid map or calibrated sensor rig.")

    if mission.speed_mps is not None and _safe_positive_float(mission.speed_mps) is None:
        blockers.append("Warehouse mission speed must be a positive number.")
    if mission.altitude_m is not None and _safe_positive_float(mission.altitude_m) is None:
        blockers.append("Warehouse mission altitude must be a positive number.")

    if not readiness.bridge_reachable:
        blockers.append(readiness.detail or "Warehouse ROS bridge is not reachable.")
    if not readiness.can_localize:
        blockers.append("Warehouse local odometry / SLAM is not ready.")
    if not readiness.nvblox_ready:
        blockers.append("Nvblox ESDF/costmap is not ready.")
    if not perception_stability_ok:
        blockers.append("Perception stability window has not passed.")
    if readiness.can_localize and not slam_stability_ok:
        blockers.append("SLAM stability window has not passed.")

    ready_to_arm = bool(readiness.bridge_reachable and readiness.can_localize)
    ready_to_takeoff = not blockers
    configured = bool(getattr(status, "configured", False))
    bridge_url = getattr(status, "bridge_url", None)

    subsystems = {
        "mission": {
            "status": "OK" if mission.loaded and mission.valid else "BLOCKED",
            "message": "Mission context loaded" if mission.loaded and mission.valid else "Mission context incomplete",
            "details": {
                "loaded": mission.loaded,
                "valid": mission.valid,
                "speed_mps": mission.speed_mps,
                "altitude_m": mission.altitude_m,
            },
        },
        "bridge": {
            "status": "OK" if readiness.bridge_reachable else "BLOCKED",
            "message": readiness.detail
            or ("Bridge reachable" if readiness.bridge_reachable else "Bridge not reachable"),
            "details": {"configured": configured, "bridge_url": bridge_url},
        },
        "slam": {
            "status": "OK" if readiness.can_localize and slam_stability_ok else "BLOCKED",
            "message": (
                "Local odometry / SLAM ready"
                if readiness.can_localize and slam_stability_ok
                else "Local odometry / SLAM unavailable or unstable"
            ),
            "details": {
                "stable_for_ms": slam_stable_for_ms,
                "required_stable_ms": slam_required_stable_ms,
            },
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
        ready_to_arm=ready_to_arm,
        ready_to_takeoff=ready_to_takeoff,
        ready_for_autonomy=ready_to_takeoff,
        overall_status="READY" if ready_to_takeoff else "BLOCKED",
        current_state="READY" if ready_to_takeoff else "WAITING",
        subsystems=subsystems,
        blocking_reasons=blockers,
        slam_stable_for_ms=slam_stable_for_ms,
        slam_required_stable_ms=slam_required_stable_ms,
        perception_stable_for_ms=perception_stable_for_ms,
        perception_required_stable_ms=perception_required_stable_ms,
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

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import (
    SubsystemHealth,
    SubsystemStatus,
    check_autopilot,
    check_bridge,
    check_failsafe,
    check_nvblox,
    check_planner,
    check_sensors,
    check_slam,
)
from backend.modules.warehouse.service.perception_stability import (
    get_perception_stability_tracker,
    perception_core_ok,
)

logger = logging.getLogger(__name__)


class OverallReadinessStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    WAITING = "WAITING"


@dataclass
class SlamStabilityTracker:
    """Tracks continuous SLAM-OK duration for takeoff gating."""

    _stable_since: float | None = field(default=None, init=False, repr=False)
    _last_slam_ok: bool = field(default=False, init=False, repr=False)
    _last_log_at: float = field(default=0.0, init=False, repr=False)

    def reset(self) -> None:
        self._stable_since = None
        self._last_slam_ok = False

    def stable_for_ms(self, *, slam_ok: bool) -> int:
        now = time.monotonic()
        if slam_ok:
            if self._stable_since is None:
                self._stable_since = now
            self._last_slam_ok = True
        else:
            if self._last_slam_ok:
                logger.info("SLAM stability timer reset (tracking not OK)")
            self._stable_since = None
            self._last_slam_ok = False

        if self._stable_since is None:
            return 0
        return max(0, int((now - self._stable_since) * 1000.0))

    def maybe_log_progress(self, *, stable_ms: int, required_ms: int) -> None:
        now = time.monotonic()
        if now - self._last_log_at < 5.0:
            return
        self._last_log_at = now
        if stable_ms > 0 and stable_ms < required_ms:
            logger.info(
                "SLAM stability progress stable_for_ms=%s required_ms=%s",
                stable_ms,
                required_ms,
            )


_SLAM_STABILITY = SlamStabilityTracker()


def get_slam_stability_tracker() -> SlamStabilityTracker:
    return _SLAM_STABILITY


def _worst_status(*statuses: SubsystemStatus) -> OverallReadinessStatus:
    order = {
        SubsystemStatus.FAIL: 4,
        SubsystemStatus.WARN: 3,
        SubsystemStatus.WAITING: 2,
        SubsystemStatus.UNKNOWN: 1,
        SubsystemStatus.OK: 0,
    }
    worst = SubsystemStatus.OK
    for status in statuses:
        if order[status] > order[worst]:
            worst = status
    if worst == SubsystemStatus.OK:
        return OverallReadinessStatus.OK
    if worst == SubsystemStatus.WARN:
        return OverallReadinessStatus.WARN
    if worst == SubsystemStatus.WAITING:
        return OverallReadinessStatus.WAITING
    return OverallReadinessStatus.FAIL


def _blocking_reasons(
    *,
    ready_to_arm: bool,
    ready_to_takeoff: bool,
    ready_for_autonomy: bool,
    subsystems: dict[str, SubsystemHealth],
    perception_stable_for_ms: int = 0,
    perception_required_stable_ms: int = 0,
) -> list[str]:
    reasons: list[str] = []
    if ready_for_autonomy:
        return reasons

    if not ready_to_arm:
        for key in ("bridge", "autopilot", "failsafe"):
            health = subsystems.get(key)
            if health and health.status in {SubsystemStatus.FAIL, SubsystemStatus.WARN}:
                reasons.append(f"{key}: {health.message}")

    if ready_to_arm and not ready_to_takeoff:
        for key in ("sensors", "slam"):
            health = subsystems.get(key)
            if health and health.status != SubsystemStatus.OK:
                reasons.append(health.message)
        nvblox = subsystems.get("nvblox")
        if nvblox and nvblox.status == SubsystemStatus.FAIL:
            reasons.append(nvblox.message)
        if perception_stable_for_ms < perception_required_stable_ms:
            remaining_s = (perception_required_stable_ms - perception_stable_for_ms) / 1000.0
            reasons.append(
                f"Core perception not stable long enough "
                f"({perception_stable_for_ms}ms / {perception_required_stable_ms}ms, "
                f"~{remaining_s:.1f}s remaining)"
            )

    if ready_to_takeoff and not ready_for_autonomy:
        planner = subsystems.get("planner")
        if planner and planner.status != SubsystemStatus.OK:
            reasons.append(planner.message)
        nvblox = subsystems.get("nvblox")
        if (nvblox and nvblox.status in {SubsystemStatus.FAIL, SubsystemStatus.WARN}) or (nvblox and nvblox.status == SubsystemStatus.WAITING):
            reasons.append(nvblox.message)

    return reasons


@dataclass(frozen=True)
class WarehouseFlightReadiness:
    ready_to_arm: bool
    ready_to_takeoff: bool
    ready_for_autonomy: bool
    overall_status: OverallReadinessStatus
    subsystems: dict[str, SubsystemHealth]
    blocking_reasons: list[str]
    updated_at: datetime
    slam_stable_for_ms: int = 0
    slam_required_stable_ms: int = 0
    perception_stable_for_ms: int = 0
    perception_required_stable_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready_to_arm": self.ready_to_arm,
            "ready_to_takeoff": self.ready_to_takeoff,
            "ready_for_autonomy": self.ready_for_autonomy,
            "overall_status": self.overall_status.value,
            "subsystems": {key: value.to_dict() for key, value in self.subsystems.items()},
            "blocking_reasons": self.blocking_reasons,
            "updated_at": self.updated_at.isoformat(),
            "slam_stable_for_ms": self.slam_stable_for_ms,
            "slam_required_stable_ms": self.slam_required_stable_ms,
            "perception_stable_for_ms": self.perception_stable_for_ms,
            "perception_required_stable_ms": self.perception_required_stable_ms,
        }


def compute_warehouse_flight_readiness(
    *,
    bridge: SubsystemHealth,
    autopilot: SubsystemHealth,
    sensors: SubsystemHealth,
    slam: SubsystemHealth,
    nvblox: SubsystemHealth,
    planner: SubsystemHealth,
    failsafe: SubsystemHealth,
    config: WarehouseFlightConfig,
    stable_for_ms: int,
    perception_stable_for_ms: int,
    mapping_stack_running: bool = False,
) -> WarehouseFlightReadiness:
    subsystems = {
        "bridge": bridge,
        "autopilot": autopilot,
        "sensors": sensors,
        "slam": slam,
        "nvblox": nvblox,
        "planner": planner,
        "failsafe": failsafe,
    }

    ready_to_arm = (
        bridge.status == SubsystemStatus.OK
        and autopilot.status in {SubsystemStatus.OK, SubsystemStatus.WARN}
        and failsafe.status in {SubsystemStatus.OK, SubsystemStatus.WARN}
    )
    battery = autopilot.details.get("battery_percent")
    if isinstance(battery, (int, float)) and float(battery) < config.min_battery_percent:
        ready_to_arm = False

    ready_to_takeoff = (
        ready_to_arm
        and sensors.status in {SubsystemStatus.OK, SubsystemStatus.WARN}
        and slam.status == SubsystemStatus.OK
    )
    if nvblox.status == SubsystemStatus.FAIL:
        ready_to_takeoff = False
    if config.require_nvblox_for_autonomy and mapping_stack_running:
        if nvblox.status != SubsystemStatus.OK:
            ready_to_takeoff = False
    if slam.status != SubsystemStatus.OK:
        ready_to_takeoff = False
    if sensors.status == SubsystemStatus.FAIL:
        ready_to_takeoff = False
    if perception_stable_for_ms < config.perception_required_stable_ms:
        ready_to_takeoff = False

    ready_for_autonomy = (
        ready_to_takeoff
        and planner.status == SubsystemStatus.OK
        and failsafe.status == SubsystemStatus.OK
    )
    if mapping_stack_running and config.require_nvblox_for_autonomy:
        if nvblox.status != SubsystemStatus.OK:
            ready_for_autonomy = False
    elif config.require_nvblox_for_autonomy:
        ready_for_autonomy = False
    if config.require_mission_for_autonomy and planner.status != SubsystemStatus.OK:
        ready_for_autonomy = False

    overall = _worst_status(*(health.status for health in subsystems.values()))
    if ready_for_autonomy:
        overall = OverallReadinessStatus.OK
    elif ready_to_takeoff:
        overall = OverallReadinessStatus.WARN if planner.status == SubsystemStatus.WAITING else overall

    blocking = _blocking_reasons(
        ready_to_arm=ready_to_arm,
        ready_to_takeoff=ready_to_takeoff,
        ready_for_autonomy=ready_for_autonomy,
        subsystems=subsystems,
        perception_stable_for_ms=perception_stable_for_ms,
        perception_required_stable_ms=config.perception_required_stable_ms,
    )

    return WarehouseFlightReadiness(
        ready_to_arm=ready_to_arm,
        ready_to_takeoff=ready_to_takeoff,
        ready_for_autonomy=ready_for_autonomy,
        overall_status=overall,
        subsystems=subsystems,
        blocking_reasons=blocking,
        updated_at=datetime.now(UTC),
        slam_stable_for_ms=stable_for_ms,
        slam_required_stable_ms=config.slam_required_stable_ms,
        perception_stable_for_ms=perception_stable_for_ms,
        perception_required_stable_ms=config.perception_required_stable_ms,
    )


def evaluate_subsystems_from_components(
    *,
    status: Any,
    components: dict[str, Any],
    telemetry: Any | None,
    config: WarehouseFlightConfig,
    mission_loaded: bool = False,
    mission_valid: bool = False,
    speed_mps: float | None = None,
    altitude_m: float | None = None,
    stability_tracker: SlamStabilityTracker | None = None,
    mapping_stack_running: bool = False,
) -> WarehouseFlightReadiness:
    tracker = stability_tracker or get_slam_stability_tracker()
    perception_tracker = get_perception_stability_tracker()

    bridge = check_bridge(status, components)
    autopilot = check_autopilot(telemetry=telemetry, components=components, config=config)
    sensors = check_sensors(components, config)

    pre_slam_ok = (
        components.get("slam_tracking_ok") is not False
        and sensors.status != SubsystemStatus.FAIL
        and bridge.status == SubsystemStatus.OK
    )
    stable_ms = tracker.stable_for_ms(slam_ok=bool(pre_slam_ok))
    tracker.maybe_log_progress(
        stable_ms=stable_ms,
        required_ms=config.slam_required_stable_ms,
    )
    slam = check_slam(components, config, stable_for_ms=stable_ms)
    nvblox = check_nvblox(
        components,
        config,
        mapping_stack_running=mapping_stack_running,
    )
    planner = check_planner(
        mission_loaded=mission_loaded,
        mission_valid=mission_valid,
        speed_mps=speed_mps,
        altitude_m=altitude_m,
        config=config,
    )
    failsafe = check_failsafe()

    core_ok = perception_core_ok(
        bridge=bridge,
        sensors=sensors,
        slam=slam,
        nvblox=nvblox,
        components=components,
        require_nvblox=config.require_nvblox_for_autonomy,
        mapping_stack_running=mapping_stack_running,
    )
    perception_stable_ms = perception_tracker.stable_for_ms(perception_ok=core_ok)
    perception_tracker.maybe_log_progress(
        stable_ms=perception_stable_ms,
        required_ms=config.perception_required_stable_ms,
    )

    readiness = compute_warehouse_flight_readiness(
        bridge=bridge,
        autopilot=autopilot,
        sensors=sensors,
        slam=slam,
        nvblox=nvblox,
        planner=planner,
        failsafe=failsafe,
        config=config,
        stable_for_ms=stable_ms,
        perception_stable_for_ms=perception_stable_ms,
        mapping_stack_running=mapping_stack_running,
    )
    logger.debug(
        "Warehouse flight readiness arm=%s takeoff=%s autonomy=%s overall=%s blocking=%s",
        readiness.ready_to_arm,
        readiness.ready_to_takeoff,
        readiness.ready_for_autonomy,
        readiness.overall_status.value,
        readiness.blocking_reasons,
    )
    return readiness

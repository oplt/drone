from __future__ import annotations

import time

from backend.modules.warehouse.service.flight_config import WarehouseFlightConfig
from backend.modules.warehouse.service.flight_health import SubsystemHealth, SubsystemStatus
from backend.modules.warehouse.service.perception_stability import (
    PerceptionStabilityTracker,
    perception_core_ok,
)


def _ok_health(message: str = "ok") -> SubsystemHealth:
    return SubsystemHealth(SubsystemStatus.OK, message)


def test_perception_stability_tracker_resets_on_drop() -> None:
    tracker = PerceptionStabilityTracker()
    assert tracker.stable_for_ms(perception_ok=True) >= 0
    time.sleep(0.05)
    stable_ms = tracker.stable_for_ms(perception_ok=True)
    assert stable_ms >= 40
    tracker.stable_for_ms(perception_ok=False)
    assert tracker.stable_for_ms(perception_ok=True) == 0


def test_perception_core_ok_requires_all_subsystems() -> None:
    config = WarehouseFlightConfig(require_nvblox_for_autonomy=True)
    assert perception_core_ok(
        bridge=_ok_health(),
        sensors=_ok_health(),
        slam=_ok_health(),
        nvblox=_ok_health(),
        components={},
        require_nvblox=config.require_nvblox_for_autonomy,
    )
    assert not perception_core_ok(
        bridge=_ok_health(),
        sensors=SubsystemHealth(SubsystemStatus.FAIL, "depth not publishing"),
        slam=_ok_health(),
        nvblox=_ok_health(),
        components={},
        require_nvblox=config.require_nvblox_for_autonomy,
    )


def test_diagnostics_pending_blocks_core_ok() -> None:
    assert not perception_core_ok(
        bridge=_ok_health(),
        sensors=_ok_health(),
        slam=_ok_health(),
        nvblox=_ok_health(),
        components={"probe_in_progress": True, "cache_ready": False},
        require_nvblox=False,
    )

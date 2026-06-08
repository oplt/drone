from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.service.safety import WarehouseSafetyDecision


@dataclass(frozen=True)
class WatchdogAction:
    triggered: bool = False
    reason: str | None = None
    action: str = "continue"
    details: dict[str, Any] = field(default_factory=dict)


class WarehouseFlightWatchdog:
    def __init__(self) -> None:
        self.active = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def evaluate(self, *, components: dict[str, Any], status: Any) -> WatchdogAction:
        del status
        if components.get("emergency_stop") is True:
            return WatchdogAction(
                triggered=True,
                reason="emergency_stop",
                action="land",
                details={"components": components},
            )
        return WatchdogAction()


_WATCHDOG = WarehouseFlightWatchdog()


def get_warehouse_flight_watchdog() -> WarehouseFlightWatchdog:
    return _WATCHDOG


def apply_watchdog_to_safety_decision(action: WatchdogAction) -> WarehouseSafetyDecision:
    return WarehouseSafetyDecision(
        safe=not action.triggered,
        reason=action.reason,
        action=action.action,
        details=action.details,
    )


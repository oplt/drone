from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from backend.modules.warehouse.service.safety import WarehouseSafetyDecision


@dataclass(frozen=True)
class WatchdogAction:
    triggered: bool = False
    reason: str | None = None
    action: str = "continue"
    details: dict[str, Any] = field(default_factory=dict)


_SENSITIVE_DETAIL_KEYS = {
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "access_key",
}


def _redact_component_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>"
            if any(marker in str(key).lower() for marker in _SENSITIVE_DETAIL_KEYS)
            else _redact_component_details(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_component_details(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_component_details(item) for item in value)
    return value


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WarehouseFlightWatchdog:
    """Small in-process safety watchdog.

    The watchdog remains intentionally simple. It does not own navigation; it only
    converts telemetry/status symptoms into a conservative safety action.
    """

    def __init__(self) -> None:
        self._active = False
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @active.setter
    def active(self, value: bool) -> None:
        with self._lock:
            self._active = bool(value)

    def start(self) -> None:
        with self._lock:
            self._active = True

    def stop(self) -> None:
        with self._lock:
            self._active = False

    def evaluate(self, *, components: dict[str, Any], status: Any) -> WatchdogAction:
        safe_components = _redact_component_details(components)

        # Hard emergency stop must remain fail-safe even if the watchdog lifecycle
        # was not explicitly started.
        if components.get("emergency_stop") is True:
            return WatchdogAction(
                triggered=True,
                reason="emergency_stop",
                action="land",
                details={"components": safe_components},
            )

        with self._lock:
            active = self._active
        if not active:
            return WatchdogAction(details={"active": False})

        bridge_reachable = getattr(status, "bridge_reachable", None)
        if bridge_reachable is False:
            return WatchdogAction(
                triggered=True,
                reason="bridge_unreachable",
                action="hold_position",
                details={"components": safe_components},
            )

        battery_pct = _as_float(components.get("battery_percent"))
        if battery_pct is not None and battery_pct <= 15.0:
            return WatchdogAction(
                triggered=True,
                reason="battery_low",
                action="land",
                details={"battery_percent": battery_pct},
            )

        localization_age_ms = _as_float(components.get("localization_age_ms"))
        if localization_age_ms is not None and localization_age_ms > 1500.0:
            return WatchdogAction(
                triggered=True,
                reason="localization_stale",
                action="hold_position",
                details={"localization_age_ms": localization_age_ms},
            )

        return WatchdogAction(details={"active": True})


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

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WarehouseMissionFailure(Exception):
    """Structured warehouse mission failure for runtime and API layers."""

    reason: str
    action: str = "abort"
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    stage: str = "flight"

    def __post_init__(self) -> None:
        if self.message is None:
            self.message = self.reason

    def __str__(self) -> str:
        base = f"Warehouse mission failed ({self.reason})"
        if self.message and self.message != self.reason:
            return f"{base}: {self.message}"
        return base

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "failure_code": self.reason,
            "action": self.action,
            "message": self.message,
            "user_message": self.message,
            "developer_message": self.message,
            "stage": self.stage,
            "details": self.details,
            "severity": "error",
        }


@dataclass
class WarehouseFlightNotReadyError(Exception):
    """Raised when warehouse autonomous flight start is blocked by readiness gates."""

    blocking_reasons: list[str]
    readiness: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return "Warehouse flight not ready: " + "; ".join(self.blocking_reasons)

from __future__ import annotations

from typing import Any

from backend.modules.property_patrol.schemas import ValidationIssue, ValidationResult


class PatrolPreflightValidator:
    async def validate(self, *, route_waypoints: list[dict[str, Any]], telemetry: dict[str, Any] | None = None) -> ValidationResult:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        telemetry = telemetry or {}
        battery = telemetry.get("battery_remaining")
        gps_ok = telemetry.get("gps_ok")
        connected = telemetry.get("connected")
        if not route_waypoints:
            errors.append(ValidationIssue(code="route_not_loaded", message="Mission route has no waypoints."))
        if battery is not None and float(battery) < 30.0:
            errors.append(ValidationIssue(code="battery_low", message="Battery below minimum return threshold."))
        if gps_ok is False:
            errors.append(ValidationIssue(code="gps_degraded", message="GPS/EKF state is not healthy."))
        if connected is False:
            errors.append(ValidationIssue(code="drone_disconnected", message="Drone connection is unavailable."))
        if not telemetry:
            warnings.append(ValidationIssue(code="telemetry_unavailable", message="Live telemetry unavailable; external runtime preflight must pass before real dispatch."))
        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


preflight_validator = PatrolPreflightValidator()


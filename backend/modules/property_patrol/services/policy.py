from __future__ import annotations

import logging
from typing import Any, Iterable

from backend.modules.property_patrol.models import PropertyPatrolSite, PropertyPatrolTemplate
from backend.modules.property_patrol.schemas import ValidationIssue, ValidationResult
from backend.modules.property_patrol.services.geometry import (
    point_from_lat_lon,
    polygon_from_geojson,
    polygons_from_geojson,
)

logger = logging.getLogger(__name__)


class PropertyPatrolPolicyEngine:
    def validate_route(
        self,
        *,
        site: PropertyPatrolSite,
        template: PropertyPatrolTemplate | None,
        waypoints: Iterable[dict[str, Any]],
    ) -> ValidationResult:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        try:
            safe = polygon_from_geojson(site.flight_safe_area, name="flight_safe_area")
            no_fly = polygons_from_geojson(site.no_fly_zones or [], name="no_fly_zones")
        except ValueError as exc:
            return ValidationResult(ok=False, errors=[ValidationIssue(code="invalid_site_geometry", message=str(exc))])

        max_alt = 120.0
        min_alt = 5.0
        if template is not None:
            if not (min_alt <= float(template.altitude_m) <= max_alt):
                errors.append(ValidationIssue(code="unsafe_altitude", message="Altitude must be between 5m and 120m."))
            if not (0.5 <= float(template.speed_mps) <= 20.0):
                errors.append(ValidationIssue(code="unsafe_speed", message="Speed must be between 0.5m/s and 20m/s."))
            if not (1 <= int(template.max_mission_duration_minutes) <= 180):
                errors.append(ValidationIssue(code="unsafe_duration", message="Max duration must be 1-180 minutes."))
            if not (10.0 <= float(template.min_battery_return_percent) <= 80.0):
                errors.append(ValidationIssue(code="unsafe_battery_threshold", message="Battery return threshold must be 10-80%."))
            if template.camera_direction == "outward" and site.privacy_zones:
                warnings.append(ValidationIssue(code="privacy_camera_direction", message="Outward camera direction may capture privacy zones."))
            if template.trigger_behavior == "auto_dispatch":
                warnings.append(ValidationIssue(code="auto_dispatch_warning", message="Auto-dispatch requires policy and preflight success before movement."))

        count = 0
        for idx, wp in enumerate(waypoints):
            count += 1
            try:
                point = point_from_lat_lon(float(wp["lat"]), float(wp["lon"]))
                alt = float(wp.get("alt", template.altitude_m if template is not None else site.default_altitude_m))
            except Exception:
                errors.append(ValidationIssue(code="invalid_waypoint", message="Waypoint must contain numeric lat/lon/alt.", waypoint_index=idx))
                continue
            if not safe.covers(point):
                errors.append(ValidationIssue(code="outside_safe_area", message="Waypoint outside flight-safe area.", waypoint_index=idx))
            if any(zone.covers(point) for zone in no_fly):
                errors.append(ValidationIssue(code="inside_no_fly_zone", message="Waypoint inside no-fly zone.", waypoint_index=idx))
            if not (min_alt <= alt <= max_alt):
                errors.append(ValidationIssue(code="unsafe_altitude", message="Waypoint altitude must be between 5m and 120m.", waypoint_index=idx))
        if count == 0:
            errors.append(ValidationIssue(code="empty_route", message="Mission route has no waypoints."))
        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

    def validate_sensor_location(
        self,
        *,
        site: PropertyPatrolSite,
        approx_location: dict[str, Any] | None,
    ) -> ValidationResult:
        if approx_location is None:
            return ValidationResult(ok=True)
        try:
            safe = polygon_from_geojson(site.flight_safe_area, name="flight_safe_area")
            point = point_from_lat_lon(float(approx_location["lat"]), float(approx_location["lon"]))
        except Exception as exc:
            return ValidationResult(ok=False, errors=[ValidationIssue(code="invalid_sensor_location", message=str(exc))])
        if not safe.covers(point):
            return ValidationResult(ok=False, errors=[ValidationIssue(code="sensor_outside_safe_area", message="Sensor coordinate outside approved site safe area.")])
        return ValidationResult(ok=True)


policy_engine = PropertyPatrolPolicyEngine()


"""Pure agriculture mission safety and reproducibility rules."""

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Point, Polygon
from shapely.validation import explain_validity

from backend.modules.agriculture.presets import PRESETS


@dataclass(frozen=True)
class AgricultureValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


class AgricultureFlightProfileValidator:
    """Validate deterministic profile inputs before generic mission planning."""

    def validate(
        self,
        *,
        profile: Any,
        cruise_alt_m: float,
        field_polygon_lonlat: list[list[float]],
        route_lonlat: list[list[float]] | None = None,
        battery_budget_s: float | None = None,
        estimated_duration_s: float | None = None,
        gps_ready: bool | None = None,
        home_ready: bool | None = None,
    ) -> AgricultureValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if len(field_polygon_lonlat) < 3:
            errors.append("field_polygon_requires_three_vertices")
        else:
            try:
                ring = [(float(p[0]), float(p[1])) for p in field_polygon_lonlat]
                polygon = Polygon(ring)
                if not polygon.is_valid or polygon.area <= 0:
                    errors.append(f"invalid_field_polygon:{explain_validity(polygon)}")
                if any(abs(lon) > 180 or abs(lat) > 90 for lon, lat in ring):
                    errors.append("field_polygon_coordinate_out_of_range")
                if route_lonlat and polygon.is_valid:
                    outside = [point for point in route_lonlat if not polygon.covers(Point(point[0], point[1]))]
                    if outside:
                        errors.append("route_exits_field_boundary")
            except (TypeError, ValueError, IndexError):
                errors.append("field_polygon_coordinates_invalid")

        if not 1 <= float(cruise_alt_m) <= 500:
            errors.append("cruise_altitude_out_of_bounds")
        if not 0.1 < float(profile.speed_mps) <= 20:
            errors.append("speed_out_of_bounds")
        if profile.camera_orientation not in {"nadir", "oblique"}:
            errors.append("camera_orientation_unsupported")
        if profile.target_gsd_cm <= 0:
            errors.append("target_gsd_must_be_positive")
        if profile.front_overlap_pct > 95 or profile.side_overlap_pct > 95:
            errors.append("overlap_exceeds_safe_limit")
        if profile.preset not in PRESETS:
            errors.append("unknown_agriculture_preset")
        sensors = set(profile.sensor_inventory)
        if profile.preset == "multispectral_thermal" and not {"multispectral", "thermal"}.issubset(sensors):
            errors.append("multispectral_thermal_preset_requires_both_sensors")
        if (profile.camera_orientation == "oblique" or sensors - {"rgb"}) and not profile.calibration_ids:
            errors.append("camera_calibration_required_for_selected_sensor")
        if gps_ready is False:
            errors.append("gps_not_ready")
        if home_ready is False:
            errors.append("home_position_not_ready")
        if estimated_duration_s is not None and battery_budget_s is not None and estimated_duration_s > battery_budget_s:
            errors.append("estimated_flight_exceeds_battery_time_budget")
        if estimated_duration_s is None:
            warnings.append("battery_time_budget_not_estimated")
        if gps_ready is None:
            warnings.append("gps_home_status_deferred_to_runtime_preflight")
        if profile.camera_orientation == "oblique":
            warnings.append("oblique_capture_requires_terrain_model")
        return AgricultureValidation(errors=errors, warnings=warnings)


agriculture_validator = AgricultureFlightProfileValidator()

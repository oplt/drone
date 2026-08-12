from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import LineString, Polygon, shape
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.policy import agriculture_validator
from backend.modules.agriculture.schemas import AgricultureGridUpdateIn, AgriculturePlanIn, AgriculturePreflightIn
from backend.modules.agriculture.workflow_models import AgricultureMissionPlan, AgricultureMissionPlanRevision, AgriculturePreflightSnapshot
from backend.modules.patrol.planning import generate_grid_surveillance_plan


REQUIRED_PREFLIGHT_CHECKS = (
    ("field_boundary", "Field boundary is saved and valid"),
    ("route_coverage", "Survey route stays within the field and exclusions"),
    ("drone_connected", "Drone connection is available"),
    ("gps_ready", "GPS quality is ready"),
    ("home_ready", "Return-to-home position is ready"),
    ("camera_ready", "Camera and recording are ready"),
    ("storage_ready", "Media storage has capacity"),
    ("weather_safe", "Weather and wind are within operator limits"),
    ("permissions_granted", "Flight permissions are granted"),
    ("model_ready", "Requested analysis models are available"),
    ("calibration_ready", "Required calibration is valid"),
)


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _zone_geometry(zone: dict[str, Any]) -> Any:
    geometry = zone.get("geometry", zone)
    return shape(geometry) if isinstance(geometry, dict) else None


def _route_intersects_exclusions(route: list[list[float]], zones: list[dict[str, Any]]) -> bool:
    geometries = [geometry for zone in zones if (geometry := _zone_geometry(zone)) is not None]
    if len(route) < 2:
        return False
    route_line = LineString(route)
    return any(route_line.intersects(geometry) for geometry in geometries)


def build_plan(payload: AgriculturePlanIn) -> tuple[dict[str, Any], list[list[float]], dict[str, Any], list[str], list[str]]:
    polygon = [(float(point[0]), float(point[1])) for point in payload.field_polygon_lonlat]
    generated = generate_grid_surveillance_plan(
        polygon,
        altitude_agl_m=payload.cruise_alt_m,
        grid_spacing_m=payload.row_spacing_m,
        grid_angle_deg=payload.grid_angle_deg,
        safety_inset_m=payload.safety_inset_m,
        pattern_mode=payload.pattern_mode,
        crosshatch_angle_offset_deg=payload.crosshatch_angle_offset_deg,
        lane_strategy=payload.lane_strategy,
        start_corner=payload.start_corner,
        row_stride=payload.row_stride,
        row_phase_m=payload.row_phase_m,
    )
    route = [[float(point.lon), float(point.lat)] for point in generated.waypoints]
    validation = agriculture_validator.validate(
        profile=payload.profile,
        cruise_alt_m=payload.cruise_alt_m,
        field_polygon_lonlat=payload.field_polygon_lonlat,
        route_lonlat=route,
        estimated_duration_s=float(generated.stats.get("route_m", 0)) / payload.profile.speed_mps,
    )
    errors = list(validation.errors)
    warnings = list(validation.warnings)
    if _route_intersects_exclusions(route, payload.exclusion_zones + payload.obstacle_zones):
        errors.append("route_intersects_exclusion_or_obstacle_zone")
    estimates = {
        **generated.stats,
        "estimated_duration_s": round(float(generated.stats.get("route_m", 0)) / payload.profile.speed_mps, 1),
        "estimated_battery_count": max(1, int(float(generated.stats.get("route_m", 0)) / max(1, payload.profile.speed_mps * 900)) + 1),
        "takeoff_point_lonlat": payload.takeoff_point_lonlat,
        "landing_point_lonlat": payload.landing_point_lonlat,
        "segment_count": max(1, (len(route) + payload.max_waypoints_per_segment - 1) // payload.max_waypoints_per_segment),
        "max_waypoints_per_segment": payload.max_waypoints_per_segment,
    }
    normalized = payload.model_dump(mode="json")
    normalized["route_lonlat"] = route
    normalized["planner_version"] = "agriculture-grid.v1"
    return normalized, route, estimates, warnings, errors


def _route_length_m(route: list[list[float]]) -> float:
    import math
    total = 0.0
    for first, second in zip(route, route[1:]):
        lat = math.radians((float(first[1]) + float(second[1])) / 2)
        dx = math.radians(float(second[0]) - float(first[0])) * 6_371_000 * math.cos(lat)
        dy = math.radians(float(second[1]) - float(first[1])) * 6_371_000
        total += math.hypot(dx, dy)
    return total


def _validate_route_snapshot(plan: AgricultureMissionPlan, route: list[list[float]]) -> list[str]:
    if any(len(point) < 2 or not (-180 <= float(point[0]) <= 180) or not (-90 <= float(point[1]) <= 90) for point in route):
        return ["route_coordinates_invalid"]
    original = plan.payload_json or {}
    polygon_coords = original.get("field_polygon_lonlat") or []
    try:
        field = Polygon(polygon_coords)
        line = LineString(route)
    except Exception:
        return ["route_geometry_invalid"]
    errors = []
    if not field.is_valid or not field.covers(line):
        errors.append("route_outside_field_boundary")
    zones = list(original.get("exclusion_zones") or []) + list(original.get("obstacle_zones") or [])
    if _route_intersects_exclusions(route, zones):
        errors.append("route_intersects_exclusion_or_obstacle_zone")
    return errors


def update_plan_grid(
    plan: AgricultureMissionPlan,
    payload: AgricultureGridUpdateIn,
    *,
    user_id: int | None,
) -> AgricultureMissionPlanRevision:
    current_revision = plan.grid_revision or 1
    if payload.expected_revision != current_revision:
        raise ValueError("AGRICULTURE_GRID_REVISION_CONFLICT")
    route = [[float(point[0]), float(point[1])] for point in payload.route_lonlat]
    errors = _validate_route_snapshot(plan, route)
    if errors:
        raise ValueError(";".join(errors))
    snapshot = dict(plan.payload_json or {})
    snapshot["route_lonlat"] = route
    snapshot["grid_revision"] = current_revision + 1
    snapshot["planner_version"] = "agriculture-grid.v1-manual"
    plan.payload_json = snapshot
    plan.route_geojson = {"type": "LineString", "coordinates": route}
    plan.grid_revision = current_revision + 1
    plan.planner_version = "agriculture-grid.v1-manual"
    plan.status = "validated"
    plan.plan_hash = _hash(snapshot)
    plan.estimates_json = {**(plan.estimates_json or {}), "route_m": round(_route_length_m(route), 2), "waypoint_count": len(route)}
    return AgricultureMissionPlanRevision(
        plan_id=plan.id,
        revision=current_revision + 1,
        planner_version=plan.planner_version,
        snapshot_json=snapshot,
        grid_geojson=plan.route_geojson,
        estimates_json=plan.estimates_json,
        created_by_user_id=user_id,
    )


async def create_plan(db: AsyncSession, *, payload: AgriculturePlanIn, org_id: int | None, user_id: int | None, source_plan_id: str | None = None) -> AgricultureMissionPlan:
    normalized, route, estimates, warnings, errors = build_plan(payload)
    record = AgricultureMissionPlan(
        field_id=payload.field_id,
        org_id=org_id,
        created_by_user_id=user_id,
        source_plan_id=source_plan_id,
        status="validated" if not errors else "invalid",
        plan_hash=_hash(normalized),
        payload_json=normalized,
        route_geojson={"type": "LineString", "coordinates": route},
        estimates_json=estimates,
        warnings_json=warnings,
        validation_errors_json=errors,
        grid_revision=1,
        planner_version="agriculture-grid.v1",
    )
    db.add(record)
    await db.flush()
    db.add(AgricultureMissionPlanRevision(
        plan_id=record.id,
        revision=1,
        planner_version="agriculture-grid.v1",
        snapshot_json=normalized,
        grid_geojson=record.route_geojson,
        estimates_json=estimates,
        created_by_user_id=user_id,
    ))
    return record


async def evaluate_preflight(db: AsyncSession, *, plan: AgricultureMissionPlan, payload: AgriculturePreflightIn, org_id: int | None, user_id: int | None) -> AgriculturePreflightSnapshot:
    provided = payload.checks
    checks: list[dict[str, Any]] = []
    for code, label in REQUIRED_PREFLIGHT_CHECKS:
        value = provided.get(code)
        status = "PASS" if value is True else "BLOCK"
        checks.append({"code": code, "label": label, "status": status, "blocking": status == "BLOCK", "observed": value, "source": "operator_or_runtime"})
    if plan.status != "validated":
        checks.append({"code": "plan_validation", "label": "Plan validation", "status": "BLOCK", "blocking": True, "observed": plan.status, "source": "agriculture_planner"})
    status = "pass" if all(check["status"] == "PASS" for check in checks) else "blocked"
    fingerprint = _hash({"plan_hash": plan.plan_hash, "checks": checks})
    snapshot = AgriculturePreflightSnapshot(
        plan_id=plan.id,
        field_id=plan.field_id,
        org_id=org_id,
        requested_by_user_id=user_id,
        status=status,
        fingerprint=fingerprint,
        checks_json=checks,
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


def snapshot_is_usable(snapshot: AgriculturePreflightSnapshot) -> bool:
    return snapshot.status == "pass" and snapshot.acknowledged_at is not None and snapshot.expires_at > datetime.now(UTC)

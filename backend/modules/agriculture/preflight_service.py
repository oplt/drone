from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from shapely.geometry import Polygon

from backend.core.config.runtime import settings
from backend.modules.agriculture.sensor_models import AgricultureSensorCalibration
from backend.modules.agriculture.storage import agriculture_storage
from backend.modules.agriculture.capabilities import (
    CAPABILITIES,
    agriculture_capability_release_service,
    validate_capability_ids,
)
from backend.modules.agriculture.workflow_models import AgricultureMissionPlan, AgriculturePreflightSnapshot
from backend.modules.identity.dependencies import OrgUser
from backend.modules.missions.schemas.mission_types import Waypoint
from backend.modules.preflight.checks.service import PreflightOrchestrator
from backend.modules.vehicle_runtime.factory import get_orchestrator
from backend.modules.missions.service.mission_start import _ensure_drone_ready_for_preflight

EVALUATOR_VERSION = "agriculture-preflight.v2"
CHECK_LABELS = {
    "field_boundary": "Field boundary is saved and valid",
    "route_coverage": "Saved route stays within the field and safety zones",
    "drone_connected": "Drone connection and telemetry are available",
    "gps_ready": "GPS quality and estimator health are ready",
    "battery_ready": "Battery reserve covers the saved route",
    "camera_ready": "Camera and recording pipeline are ready",
    "storage_ready": "Media storage has sufficient capacity",
    "weather_safe": "Weather and wind are within configured limits",
    "permissions_granted": "Flight permission provider grants the mission",
    "model_ready": "Requested agriculture models are deployed",
    "calibration_ready": "Required sensor calibrations are current",
}


def _check(code: str, status: str, message: str, *, observed: Any = None, source: str, remediation: str) -> dict[str, Any]:
    return {"code": code, "label": CHECK_LABELS[code], "status": status, "blocking": status == "BLOCK", "message": message, "observed": observed, "source": source, "evaluated_at": datetime.now(UTC).isoformat(), "remediation": remediation}


def _status(results: list[dict[str, Any]]) -> str:
    if any(row["status"] == "BLOCK" for row in results):
        return "blocked"
    if any(row["status"] == "WARN" for row in results):
        return "warning"
    return "pass"


def _report_status(report: Any, names: set[str]) -> tuple[str, str]:
    rows = [row for row in [*(report.base_checks or []), *(report.mission_checks or [])] if row.name in names]
    if not rows:
        return "BLOCK", "Authoritative runtime check did not return a result."
    states = [getattr(row.status, "value", str(row.status)) for row in rows]
    if "FAIL" in states:
        return "BLOCK", next((row.message for row, state in zip(rows, states) if state == "FAIL" and row.message), "Runtime check failed.")
    if any(state in {"WARN", "SKIP"} for state in states):
        return "WARN" if "WARN" in states else "BLOCK", next((row.message for row in rows if row.message), "Runtime check is incomplete.")
    return "PASS", next((row.message for row in rows if row.message), "Runtime check passed.")


def _runtime_overrides() -> dict[str, Any]:
    return {"GPS_FIX_TYPE_MIN": settings.GPS_FIX_TYPE_MIN, "HDOP_MAX": settings.HDOP_MAX, "SAT_MIN": settings.SAT_MIN, "HOME_MAX_DIST": settings.HOME_MAX_DIST, "BATTERY_MIN_V": settings.BATTERY_MIN_V, "BATTERY_MIN_PERCENT": settings.BATTERY_MIN_PERCENT, "BATTERY_RESERVE_PCT": settings.BATTERY_MIN_PERCENT, "HEARTBEAT_MAX_AGE": settings.HEARTBEAT_MAX_AGE, "MSG_RATE_MIN_HZ": settings.MSG_RATE_MIN_HZ, "WEATHER_PREFLIGHT_ENABLED": settings.weather_preflight_enabled, "WEATHER_API_FAIL_POLICY": settings.weather_api_fail_policy, "WIND_MAX": settings.WIND_MAX, "GUST_MAX": settings.GUST_MAX, "WEATHER_MAX_PRECIP_MM": settings.weather_max_precip_mm, "WEATHER_MIN_VISIBILITY_M": settings.weather_min_visibility_m, "WEATHER_BLOCKED_CODES": settings.weather_blocked_codes}


async def _runtime_checks(plan: AgricultureMissionPlan) -> tuple[list[dict[str, Any]], Any | None, Any | None]:
    try:
        orch = await get_orchestrator()
    except Exception as exc:
        return [_check("drone_connected", "BLOCK", f"Runtime unavailable: {exc}", source="vehicle_runtime", remediation="Start or reconnect the vehicle runtime.")] + [_check(code, "BLOCK", "Cannot evaluate without the vehicle runtime.", source="vehicle_runtime", remediation="Restore the vehicle runtime and refresh.") for code in ("gps_ready", "battery_ready")], None, None
    try:
        await _ensure_drone_ready_for_preflight(orch, profile=type("Profile", (), {"allows_home_fallback": False})())
        telemetry = await asyncio.wait_for(orch.async_drone.get_telemetry(), timeout=15)
    except Exception as exc:
        return [_check("drone_connected", "BLOCK", f"Drone telemetry unavailable: {exc}", source="vehicle_runtime", remediation="Connect the drone and retry server preflight.")] + [_check(code, "BLOCK", "Cannot evaluate without authoritative drone telemetry.", source="vehicle_runtime", remediation="Restore the drone connection and refresh.") for code in ("gps_ready", "battery_ready")], orch, None
    route = (plan.route_geojson or {}).get("coordinates") or []
    mission = {"type": "route", "waypoints": [{"lon": point[0], "lat": point[1], "alt": plan.payload_json.get("cruise_alt_m", 30)} for point in route], "speed": plan.payload_json.get("profile", {}).get("speed_mps", 5), "altitude_agl": plan.payload_json.get("cruise_alt_m", 30)}
    field = plan.payload_json.get("field_polygon_lonlat") or []
    try:
        report = await asyncio.wait_for(PreflightOrchestrator(config=_runtime_overrides()).run(telemetry, mission, geofence_polygon=[Waypoint(lon=point[0], lat=point[1], alt=plan.payload_json.get("cruise_alt_m", 30)) for point in field]), timeout=30)
    except Exception as exc:
        return [_check(code, "BLOCK", f"Authoritative runtime evaluation failed: {exc}", source="runtime_preflight", remediation="Resolve runtime/preflight provider errors and refresh.") for code in ("gps_ready", "battery_ready", "weather_safe", "route_coverage")], orch, telemetry
    checks: list[dict[str, Any]] = []
    for code, names, remediation in (("gps_ready", {"GPS Fix Type", "EKF Health", "Home Position"}, "Acquire a stable GPS fix and home position."), ("battery_ready", {"Battery Voltage", "Battery Budget (%)", "Battery Budget (Ah)", "Battery"}, "Charge or replace the battery and rerun the route estimate."), ("weather_safe", {"Weather Availability"}, "Wait for safe weather or resolve the weather provider.")):
        state, message = _report_status(report, names)
        checks.append(_check(code, state, message, source="runtime_preflight", remediation=remediation))
    return checks, orch, telemetry


async def evaluate_server_preflight(db: AsyncSession, *, plan: AgricultureMissionPlan, user: OrgUser) -> AgriculturePreflightSnapshot:
    now = datetime.now(UTC)
    payload = plan.payload_json or {}
    checks: list[dict[str, Any]] = []
    field = payload.get("field_polygon_lonlat") or []
    try:
        valid_field = len(field) >= 3 and Polygon(field).is_valid and Polygon(field).area > 0
    except Exception:
        valid_field = False
    checks.append(_check("field_boundary", "PASS" if valid_field and plan.status != "invalid" else "BLOCK", "Boundary and plan snapshot are valid." if valid_field and plan.status != "invalid" else "Saved field boundary or plan is invalid.", observed={"vertices": len(field), "plan_status": plan.status}, source="agriculture_plan_snapshot", remediation="Fix the field boundary and save a new validated plan."))
    route_errors = set(plan.validation_errors_json or [])
    coverage_ok = plan.status == "validated" and not route_errors
    checks.append(_check("route_coverage", "PASS" if coverage_ok else "BLOCK", "Saved route passed server route validation." if coverage_ok else "Saved route has validation errors.", observed={"revision": plan.grid_revision, "errors": sorted(route_errors)}, source="agriculture_plan_snapshot", remediation="Regenerate or edit the grid, then rerun validation."))
    runtime_checks, orch, telemetry = await _runtime_checks(plan)
    if telemetry is not None:
        checks.append(_check("drone_connected", "PASS", "Authoritative telemetry was read from the vehicle runtime.", observed={"type": type(telemetry).__name__}, source="vehicle_runtime", remediation="Connect the drone and retry server preflight."))
    checks.extend(runtime_checks)
    if not any(row["code"] == "weather_safe" for row in checks):
        checks.append(_check("weather_safe", "BLOCK", "Authoritative weather evaluation was unavailable.", source="weather_provider", remediation="Refresh when the configured weather provider is available."))
    camera_ok = bool(getattr(orch, "video", None)) if orch is not None else False
    checks.append(_check("camera_ready", "PASS" if camera_ok else "BLOCK", "Runtime video/camera adapter is available." if camera_ok else "Runtime video/camera adapter is unavailable.", observed={"adapter": type(getattr(orch, "video", None)).__name__ if orch is not None and getattr(orch, "video", None) else None}, source="vehicle_runtime", remediation="Connect a camera and verify the recording adapter."))
    try:
        storage_ok, storage_free = agriculture_storage.health()
        free_bytes = storage_free or 0
    except Exception:
        storage_ok, free_bytes = False, 0
    checks.append(_check("storage_ready", "PASS" if storage_ok and (free_bytes == 0 or free_bytes >= 100 * 1024 * 1024) else "BLOCK", f"{free_bytes} bytes available." if storage_ok else "Agriculture storage is unavailable.", observed={"free_bytes": free_bytes, "backend": getattr(settings, "storage_backend", "local")}, source="agriculture_storage", remediation="Provision the configured agriculture object-storage bucket and verify credentials."))
    checks.append(_check("permissions_granted", "BLOCK", "No authoritative flight-permission provider is configured.", source="permission_provider", remediation="Configure the jurisdiction permission integration before launch."))
    raw_requested = payload.get("profile", {}).get("requested_analyses", [])
    invalid_capabilities: str | None = None
    try:
        requested = validate_capability_ids(raw_requested)
    except ValueError as exc:
        requested = []
        invalid_capabilities = str(exc)
    required_models = {
        item for item in requested if CAPABILITIES[item].requires_model
    }
    releases = await agriculture_capability_release_service.active_release_snapshots(
        db,
        org_id=user.org_id,
        user_id=user.user.id,
        capability_ids=required_models,
    )
    missing_models = sorted(required_models - set(releases))
    model_ready = invalid_capabilities is None and not missing_models
    message = "All requested model capabilities are released."
    if invalid_capabilities:
        message = invalid_capabilities
    elif missing_models:
        message = f"Missing production releases: {', '.join(missing_models)}."
    checks.append(_check("model_ready", "PASS" if model_ready else "BLOCK", message, observed={"requested": requested, "available": sorted(releases)}, source="vision_capability_releases", remediation="Deploy an eligible Vision model for every requested model-backed capability or remove it from the plan."))
    profile = payload.get("profile", {})
    sensors = set(profile.get("sensor_inventory") or ["rgb"])
    calibration_ids = set(profile.get("calibration_ids") or [])
    calibrations = list((await db.scalars(select(AgricultureSensorCalibration).where(AgricultureSensorCalibration.id.in_(calibration_ids), AgricultureSensorCalibration.org_id == user.org_id))).all()) if calibration_ids else []
    valid_calibrations = {row.id for row in calibrations if (row.valid_until is None or row.valid_until > now) and (row.valid_from is None or row.valid_from <= now)}
    calibration_ok = sensors <= {"rgb"} or calibration_ids and valid_calibrations == calibration_ids
    checks.append(_check("calibration_ready", "PASS" if calibration_ok else "BLOCK", "Required sensor calibrations are current." if calibration_ok else "Required calibration is missing, expired or not owned by this organization.", observed={"sensors": sorted(sensors), "valid_ids": sorted(valid_calibrations)}, source="agriculture_sensor_calibration_registry", remediation="Register current calibration artifacts for every non-RGB sensor."))
    status = _status(checks)
    fingerprint = __import__("hashlib").sha256(__import__("json").dumps({"plan_hash": plan.plan_hash, "checks": checks}, sort_keys=True, default=str).encode()).hexdigest()
    snapshot = AgriculturePreflightSnapshot(plan_id=plan.id, field_id=plan.field_id, org_id=user.org_id, requested_by_user_id=user.user.id, status=status, fingerprint=fingerprint, evaluator_version=EVALUATOR_VERSION, checks_json=checks, expires_at=now + timedelta(minutes=15))
    db.add(snapshot)
    await db.flush()
    return snapshot

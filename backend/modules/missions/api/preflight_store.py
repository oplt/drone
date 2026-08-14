from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.core.config.runtime import env_truthy, settings
from backend.modules.missions.api.mission_route_schemas import PreflightRunOut
from backend.modules.missions.application import mission_application
from backend.modules.missions.schemas.mission_create import MissionCreateIn
from backend.modules.missions.service.mission_builder import flight_profile_for_payload
from backend.modules.missions.service.mission_start import (
    _ensure_drone_ready_for_preflight,
    preflight_allows_start,
)
from backend.modules.preflight.checks.schemas import PreflightReport

PREFLIGHT_RUN_TTL_SECONDS = max(60, settings.preflight_run_ttl_seconds)
REQUIRE_PREFLIGHT_RUN_BEFORE_MISSION = env_truthy(settings.require_preflight_run_before_mission)


@dataclass
class PreflightRunRecord:
    run_id: str
    user_id: int
    mission_fingerprint: str
    overall_status: str
    created_at: float
    expires_at: float
    report: dict

    @classmethod
    def from_db(cls, row: Any) -> PreflightRunRecord:
        created_ts = (
            row.created_at.timestamp()
            if isinstance(row.created_at, datetime)
            else float(row.created_at or 0)
        )
        expires_ts = (
            row.expires_at.timestamp()
            if isinstance(row.expires_at, datetime)
            else (created_ts + PREFLIGHT_RUN_TTL_SECONDS)
        )
        report_raw = {
            "mission_type": row.mission_type,
            "overall_status": row.overall_status,
            "base_checks": row.base_checks or [],
            "mission_checks": row.mission_checks or [],
            "critical_failures": [
                {"name": name, "status": "FAIL", "message": None}
                for name in (row.critical_failures or [])
            ],
            "summary": row.summary or {},
        }
        return cls(
            run_id=row.run_uuid,
            user_id=row.user_id or 0,
            mission_fingerprint=row.mission_fingerprint or "",
            overall_status=row.overall_status,
            created_at=created_ts,
            expires_at=expires_ts,
            report=report_raw,
        )


async def run_preflight_report(
    orch: Any,
    payload: MissionCreateIn,
    *,
    mission: Any,
    mission_data_override: dict[str, object] | None,
) -> PreflightReport:
    profile = flight_profile_for_payload(payload)
    await _ensure_drone_ready_for_preflight(orch, profile=profile)
    return await orch._run_preflight_checks(
        mission.get_waypoints(),
        payload.cruise_alt,
        raise_on_fail=False,
        mission_data=mission_data_override,
        config_overrides={"FLIGHT_ENVIRONMENT": profile.environment.value},
    )


async def store_preflight_run(
    *,
    user_id: int,
    mission_fingerprint: str,
    report: PreflightReport,
) -> PreflightRunRecord:
    now = time.time()
    run_uuid = f"pf_{int(now)}_{uuid.uuid4().hex[:10]}"
    report_dump = report.model_dump(mode="json")
    expires_at_dt = datetime.fromtimestamp(now + PREFLIGHT_RUN_TTL_SECONDS, tz=UTC)
    db_row = await mission_application.create_preflight(
        run_uuid=run_uuid,
        user_id=user_id,
        mission_type=str(report.mission_type or ""),
        mission_name=None,
        mission_fingerprint=mission_fingerprint,
        overall_status=str(report.overall_status),
        base_checks=report_dump.get("base_checks", []),
        mission_checks=report_dump.get("mission_checks", []),
        critical_failures=[check["name"] for check in (report_dump.get("critical_failures") or [])],
        summary=report_dump.get("summary") or {},
        expires_at=expires_at_dt,
        completed_at=datetime.now(UTC),
    )
    return PreflightRunRecord.from_db(db_row)


async def get_preflight_run_record(run_id: str) -> PreflightRunRecord | None:
    db_row = await mission_application.get_preflight(run_id)
    if db_row is None:
        return None
    if db_row.expires_at and db_row.expires_at < datetime.now(UTC):
        return None
    return PreflightRunRecord.from_db(db_row)


def preflight_record_out(rec: PreflightRunRecord) -> PreflightRunOut:
    return PreflightRunOut(
        preflight_run_id=rec.run_id,
        mission_fingerprint=rec.mission_fingerprint,
        overall_status=rec.overall_status,
        can_start_mission=preflight_allows_start(rec.overall_status),
        created_at=rec.created_at,
        expires_at=rec.expires_at,
        report=PreflightReport.model_validate(rec.report),
    )

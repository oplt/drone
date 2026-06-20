from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity.models import User
from backend.modules.missions.schemas.mission_create import MissionCreateIn
from backend.modules.missions.service.mission_start import start_mission_for_user
from backend.modules.property_patrol.models import (
    PropertyPatrolRun,
    PropertyPatrolSite,
    PropertyPatrolTemplate,
)
from backend.modules.property_patrol.schemas import ValidationIssue, ValidationResult
from backend.modules.property_patrol.services.policy import policy_engine
from backend.modules.property_patrol.services.preflight import preflight_validator
from backend.modules.property_patrol.services.state_machine import state_machine

logger = logging.getLogger(__name__)


class PatrolDispatchService:
    async def create_validated_run(
        self,
        *,
        db: AsyncSession,
        site: PropertyPatrolSite,
        template: PropertyPatrolTemplate | None,
        route_waypoints: list[dict[str, Any]],
        mission_type: str,
        operator_id: int | None,
        drone_id: str | None = None,
    ) -> tuple[PropertyPatrolRun, ValidationResult]:
        validation = policy_engine.validate_route(
            site=site, template=template, waypoints=route_waypoints
        )
        run = PropertyPatrolRun(
            site_id=site.id,
            template_id=template.id if template else None,
            mission_type=mission_type,
            state="VALIDATED" if validation.ok else "FAILED",
            route_waypoints=route_waypoints,
            operator_id=operator_id,
            drone_id=drone_id,
            failure_reason=None
            if validation.ok
            else "; ".join(err.message for err in validation.errors),
        )
        db.add(run)
        await db.flush()
        logger.info(
            "property_patrol_mission_validated", extra={"run_id": run.id, "ok": validation.ok}
        )
        return run, validation

    async def dispatch_after_preflight(
        self,
        *,
        db: AsyncSession,
        run: PropertyPatrolRun,
        telemetry: dict[str, Any] | None = None,
    ) -> ValidationResult:
        try:
            run.state = state_machine.transition(
                run.state, "PREFLIGHT_CHECK", reason="dispatch_requested"
            )
        except ValueError as exc:
            return ValidationResult(
                ok=False,
                errors=[ValidationIssue(code="invalid_state", message=str(exc))],
            )
        preflight = await preflight_validator.validate(
            route_waypoints=run.route_waypoints, telemetry=telemetry
        )
        if not preflight.ok:
            run.state = "FAILED"
            run.failure_reason = "; ".join(err.message for err in preflight.errors)
            logger.info(
                "property_patrol_preflight_failed",
                extra={"run_id": run.id, "errors": run.failure_reason},
            )
            return preflight

        run.state = state_machine.transition(run.state, "ARMED", reason="preflight_passed")
        user_id = run.operator_id
        if user_id is None:
            site = await db.get(PropertyPatrolSite, run.site_id)
            user_id = site.owner_id if site is not None else None
        user = await db.get(User, user_id) if user_id is not None else None
        if user is None:
            run.state = "FAILED"
            run.failure_reason = "No authorized dispatch user is associated with this patrol."
            return ValidationResult(
                ok=False,
                errors=[ValidationIssue(code="dispatch_user_missing", message=run.failure_reason)],
            )

        altitude = float(run.route_waypoints[0].get("alt", 30.0))
        payload = MissionCreateIn.model_validate(
            {
                "name": f"Property patrol {run.id}",
                "mission_type": "waypoint",
                "cruise_alt": altitude,
                "waypoints": run.route_waypoints,
            }
        )
        try:
            launch = await start_mission_for_user(payload, user=user)
        except Exception as exc:
            run.state = "FAILED"
            run.failure_reason = str(exc)[:512]
            logger.exception("property_patrol_runtime_dispatch_failed", extra={"run_id": run.id})
            return ValidationResult(
                ok=False,
                errors=[
                    ValidationIssue(
                        code="runtime_dispatch_failed",
                        message="Mission runtime rejected property patrol dispatch.",
                    )
                ],
            )

        run.start_time = datetime.now(UTC)
        logger.info(
            "property_patrol_mission_dispatched",
            extra={
                "run_id": run.id,
                "waypoints": len(run.route_waypoints),
                "runtime_flight_id": launch.flight_id,
            },
        )
        await db.flush()
        return preflight

    def operator_transition(self, run: PropertyPatrolRun, command: str) -> None:
        targets = {
            "approve": "PREFLIGHT_CHECK",
            "pause": "PAUSED_BY_OPERATOR",
            "resume": "PATROL",
            "abort": "ABORTED",
            "return-home": "RETURN_HOME",
            "hold": "GPS_DEGRADED_HOLD",
        }
        target = targets[command]
        run.state = state_machine.transition(run.state, target, reason=f"operator_{command}")
        if run.state in {"ABORTED", "COMPLETED", "FAILED"}:
            run.end_time = datetime.now(UTC)
        logger.info(
            "property_patrol_operator_action",
            extra={"run_id": run.id, "command": command, "state": run.state},
        )


dispatch_service = PatrolDispatchService()

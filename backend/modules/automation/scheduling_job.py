from __future__ import annotations

import logging
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select

from backend.core.database.session import Session

from .models import MissionTemplate, ScheduledRun

logger = logging.getLogger(__name__)


async def execute_scheduled_run(scheduled_run_id: int) -> None:
    async with Session() as db:
        q = await db.execute(select(ScheduledRun).where(ScheduledRun.id == scheduled_run_id))
        run = q.scalar_one_or_none()
        if run is None:
            logger.error("ScheduledRun %d not found; skipping", scheduled_run_id)
            return

        # Transition: pending to running.
        run.status = "running"
        run.started_at = datetime.now(UTC)
        await db.commit()

        try:
            q2 = await db.execute(
                select(MissionTemplate).where(MissionTemplate.id == run.template_id)
            )
            template = q2.scalar_one_or_none()
            if template is None:
                raise ValueError(f"MissionTemplate {run.template_id} not found")

            # NOTE: Actual drone dispatch requires the Orchestrator singleton
            # which lives in the API process. Until an inter-process RPC layer
            # (e.g. Redis pub/sub or a dedicated command queue) is wired up,
            # we log the intent and mark the run completed so the scheduling
            # loop makes forward progress without corrupting run state.
            logger.info(
                "STUB dispatch: template_id=%d name=%r mission_type=%r "
                "scheduled_run_id=%d; wire to Orchestrator RPC in next sprint",
                template.id,
                template.name,
                template.mission_type,
                scheduled_run_id,
            )

            run.status = "completed"
            run.ended_at = datetime.now(UTC)
            await db.commit()
            logger.info("ScheduledRun %d completed (stub)", scheduled_run_id)

        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)[:512]
            run.ended_at = datetime.now(UTC)
            await db.commit()
            raise


async def dispatch_due_templates(enqueue_run) -> None:
    now = datetime.now(UTC)

    async with Session() as db:
        q = await db.execute(
            select(MissionTemplate).where(
                MissionTemplate.is_active.is_(True),
                MissionTemplate.schedule_cron.is_not(None),
            )
        )
        templates = q.scalars().all()

        run_ids: list[int] = []
        for tmpl in templates:
            try:
                # Find the most recent completed/running run for this template
                q2 = await db.execute(
                    select(ScheduledRun)
                    .where(ScheduledRun.template_id == tmpl.id)
                    .order_by(ScheduledRun.created_at.desc())
                    .limit(1)
                )
                last_run = q2.scalar_one_or_none()

                # Base time for next-run calculation: last run's created_at or
                # template's own created_at if no run exists yet.
                base_dt: datetime
                if last_run is not None:
                    base_dt = last_run.created_at
                    # Ensure timezone-aware
                    if base_dt.tzinfo is None:
                        base_dt = base_dt.replace(tzinfo=UTC)
                else:
                    base_dt = tmpl.created_at
                    if base_dt.tzinfo is None:
                        base_dt = base_dt.replace(tzinfo=UTC)

                cron = croniter(tmpl.schedule_cron, base_dt)
                next_due: datetime = cron.get_next(datetime)
                # croniter returns naive datetime when base is naive; always
                # attach UTC so comparison is consistent.
                if next_due.tzinfo is None:
                    next_due = next_due.replace(tzinfo=UTC)

                if next_due > now:
                    # Not yet due
                    continue

                # Guard: skip if there's already a pending/running run to
                # prevent duplicate dispatches on overlapping beat ticks.
                q3 = await db.execute(
                    select(ScheduledRun).where(
                        ScheduledRun.template_id == tmpl.id,
                        ScheduledRun.status.in_(["pending", "running"]),
                    )
                )
                in_flight = q3.scalar_one_or_none()
                if in_flight is not None:
                    logger.debug(
                        "Template %d already has an active run (%d); skipping dispatch",
                        tmpl.id,
                        in_flight.id,
                    )
                    continue

                # Create the ScheduledRun and enqueue
                run = ScheduledRun(
                    template_id=tmpl.id,
                    triggered_by="schedule",
                    status="pending",
                )
                db.add(run)
                await db.flush()  # Get run.id before commit

                run_ids.append(run.id)
                logger.info(
                    "Scheduled dispatch prepared: template_id=%d name=%r scheduled_run_id=%d",
                    tmpl.id,
                    tmpl.name,
                    run.id,
                )

            except Exception:
                logger.exception("check_due_templates: error processing template_id=%d", tmpl.id)
                # Continue to next template; do not let one bad cron expression
                # block all other templates.
                continue

        await db.commit()
        if run_ids:
            logger.info("check_due_templates: prepared %d run(s)", len(run_ids))

    for run_id in run_ids:
        enqueue_run(run_id)

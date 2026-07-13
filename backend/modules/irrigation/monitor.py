from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from uuid import uuid4

from sqlalchemy import select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.infrastructure.cache.locks import distributed_lock
from backend.modules.irrigation.job_repository import IrrigationJobRepository
from backend.modules.irrigation.models import ProcessedFieldLayer
from backend.modules.irrigation.queue import enqueue_irrigation_processing
from backend.modules.irrigation.service.processing import irrigation_service
from backend.modules.missions.runtime_models import MissionRuntime

logger = logging.getLogger(__name__)


class IrrigationMonitor:
    def __init__(self) -> None:
        self.poll_interval_s = max(2.0, settings.irrigation_monitor_poll_s)
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="irrigation-monitor")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Irrigation monitor tick failed")
            await asyncio.sleep(self.poll_interval_s)

    async def _tick(self) -> None:
        async with Session() as db:
            recovered = await IrrigationJobRepository().recover_stale_running(
                db,
                stale_after_s=settings.irrigation_job_stale_after_s,
            )
            if recovered:
                logger.warning("Requeued stale irrigation jobs count=%s", recovered)
            result = await db.execute(
                select(MissionRuntime)
                .where(MissionRuntime.mission_type == "grid")
                .where(MissionRuntime.state.in_(("completed", "failed", "aborted")))
                .order_by(MissionRuntime.updated_at.desc())
                .limit(12)
            )
            missions = list(result.scalars().all())
            repository = IrrigationJobRepository()
            for mission in missions:
                captures = await irrigation_service.list_captures(
                    db, mission_id=mission.client_flight_id
                )
                if not captures:
                    continue
                layer = await db.scalar(
                    select(ProcessedFieldLayer).where(
                        ProcessedFieldLayer.mission_id == mission.client_flight_id
                    )
                )
                if layer and layer.status in {"running", "completed"}:
                    continue

                input_checksum = irrigation_service.capture_input_checksum(captures)
                lock_name = f"lock:irrigation:enqueue:{mission.client_flight_id}:{input_checksum}"
                async with distributed_lock(lock_name):
                    existing_job = await repository.find_reusable(
                        db,
                        mission_id=mission.client_flight_id,
                        input_checksum=input_checksum,
                        force=False,
                    )
                    if existing_job:
                        if not existing_job.celery_task_id:
                            try:
                                existing_job.celery_task_id = enqueue_irrigation_processing(
                                    existing_job.id
                                )
                                await db.commit()
                            except Exception as exc:
                                await repository.mark_finished(
                                    db, existing_job.id, status="failed", error=str(exc)
                                )
                                logger.exception(
                                    "Irrigation queued-job recovery failed: mission_id=%s",
                                    mission.client_flight_id,
                                )
                        continue

                    logger.info(
                        "Irrigation monitor triggering post-mission processing for %s",
                        mission.client_flight_id,
                    )
                    if layer is None:
                        layer = ProcessedFieldLayer(
                            mission_id=mission.client_flight_id,
                            org_id=mission.org_id,
                            project_id=mission.project_id,
                            status="queued",
                        )
                        db.add(layer)
                    layer.status = "queued"
                    layer.error = None
                    layer.capture_count = len(captures)
                    job = await repository.create(
                        db,
                        job_id=uuid4().hex,
                        mission_id=mission.client_flight_id,
                        org_id=mission.org_id,
                        user_id=None,
                        input_checksum=input_checksum,
                    )
                    await db.commit()
                    try:
                        job.celery_task_id = enqueue_irrigation_processing(job.id)
                        await db.commit()
                    except Exception as exc:
                        await repository.mark_finished(db, job.id, status="failed", error=str(exc))
                        layer.status = "failed"
                        layer.error = "Irrigation worker unavailable"
                        await db.commit()
                        logger.exception(
                            "Irrigation processing enqueue failed: mission_id=%s",
                            mission.client_flight_id,
                        )


irrigation_monitor = IrrigationMonitor()

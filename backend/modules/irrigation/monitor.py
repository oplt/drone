from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import select

from backend.core.database.session import Session
from backend.modules.irrigation.models import CaptureRecord, ProcessedFieldLayer
from backend.modules.irrigation.service.processing import irrigation_service
from backend.modules.missions.runtime_models import MissionRuntime

logger = logging.getLogger(__name__)


class IrrigationMonitor:
    def __init__(self) -> None:
        self.poll_interval_s = max(2.0, float(os.getenv("IRRIGATION_MONITOR_POLL_S", "10")))
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
            try:
                await self._task
            except asyncio.CancelledError:
                pass
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
            result = await db.execute(
                select(MissionRuntime)
                .where(MissionRuntime.mission_type == "grid")
                .where(MissionRuntime.state.in_(("completed", "failed", "aborted")))
                .order_by(MissionRuntime.updated_at.desc())
                .limit(12)
            )
            missions = list(result.scalars().all())
            for mission in missions:
                captures_exist = await db.scalar(
                    select(CaptureRecord.id)
                    .where(CaptureRecord.mission_id == mission.client_flight_id)
                    .limit(1)
                )
                if captures_exist is None:
                    continue
                layer = await db.scalar(
                    select(ProcessedFieldLayer).where(
                        ProcessedFieldLayer.mission_id == mission.client_flight_id
                    )
                )
                if layer and layer.status in {"running", "completed"}:
                    continue
                logger.info(
                    "Irrigation monitor triggering post-mission processing for %s",
                    mission.client_flight_id,
                )
                await irrigation_service.process_mission(db, mission=mission, force=False)


irrigation_monitor = IrrigationMonitor()

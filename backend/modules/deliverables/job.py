from __future__ import annotations

import logging

from backend.core.database.session import Session
from backend.infrastructure.deliverables import DeliverableStorage
from backend.modules.integrations.webhooks.service import WebhookDispatchService

from .job_repository import DeliverableJobRepository
from .ports import DeliverableStoragePort
from .rendering import render_deliverable

logger = logging.getLogger(__name__)


class DeliverableGenerationJob:
    def __init__(
        self,
        repository: DeliverableJobRepository | None = None,
        storage: DeliverableStoragePort | None = None,
        notifications: WebhookDispatchService | None = None,
    ) -> None:
        self.repository = repository or DeliverableJobRepository()
        self.storage = storage or DeliverableStorage()
        self.notifications = notifications or WebhookDispatchService()

    async def run(self, deliverable_id: int) -> None:
        async with Session() as db:
            try:
                loaded = await self.repository.load_for_processing(
                    db, deliverable_id=deliverable_id
                )
                if loaded is None:
                    return
                deliverable, field = loaded
                geometry = (
                    await self.repository.geojson_geometry(db, field_id=field.id)
                    if deliverable.type == "GEOJSON"
                    else None
                )
                rendered = render_deliverable(deliverable.type, field, geometry)
                url = await self.storage.save(
                    org_id=deliverable.org_id,
                    deliverable_id=deliverable.id,
                    filename=rendered.filename,
                    content=rendered.content,
                )
                await self.repository.ready(db, deliverable=deliverable, url=url)
                await self.notifications.enqueue(
                    db,
                    org_id=deliverable.org_id,
                    event_type="deliverable.ready",
                    payload={"id": deliverable.id, "field_id": field.id, "type": deliverable.type},
                    idempotency_key=f"deliverable.ready:{deliverable.id}",
                )
                await db.commit()
                logger.info("Deliverable %s generated: %s", deliverable_id, url)
            except Exception as exc:
                await db.rollback()
                await self.repository.failed(db, deliverable_id=deliverable_id, error=str(exc))
                raise

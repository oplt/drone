from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fields.models import Field

from .models import FieldDeliverable


class DeliverableJobRepository:
    async def load_for_processing(
        self, db: AsyncSession, *, deliverable_id: int
    ) -> tuple[FieldDeliverable, Field] | None:
        deliverable = await db.get(FieldDeliverable, deliverable_id)
        if deliverable is None:
            raise ValueError(f"FieldDeliverable {deliverable_id} not found")
        if deliverable.status == "ready" and deliverable.url:
            return None
        field = await db.get(Field, deliverable.field_id)
        if field is None:
            raise ValueError(f"Field {deliverable.field_id} not found")
        deliverable.status = "processing"
        deliverable.error = None
        await db.commit()
        return deliverable, field

    async def geojson_geometry(self, db: AsyncSession, *, field_id: int) -> dict | None:
        result = await db.execute(
            text("SELECT ST_AsGeoJSON(boundary)::json FROM fields WHERE id = :id"),
            {"id": field_id},
        )
        return result.scalar()

    async def ready(self, db: AsyncSession, *, deliverable: FieldDeliverable, url: str) -> None:
        deliverable.url = url
        deliverable.status = "ready"
        deliverable.error = None
        await db.flush()

    async def failed(self, db: AsyncSession, *, deliverable_id: int, error: str) -> None:
        deliverable = await db.get(FieldDeliverable, deliverable_id)
        if deliverable is not None and deliverable.status != "ready":
            deliverable.status = "failed"
            deliverable.error = error[:512]
            await db.commit()

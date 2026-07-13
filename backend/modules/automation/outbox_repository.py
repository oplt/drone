from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import OutboxEvent


class OutboxRepository:
    async def enqueue_many(
        self, db: AsyncSession, *, events: list[dict]
    ) -> list[OutboxEvent]:
        """Insert a batch of idempotent outbox events with one lookup/flush."""
        if not events:
            return []
        keys = [str(event["idempotency_key"]) for event in events]
        existing = {
            event.idempotency_key: event
            for event in (
                await db.scalars(
                    select(OutboxEvent).where(OutboxEvent.idempotency_key.in_(keys))
                )
            ).all()
        }
        result: list[OutboxEvent] = []
        for payload in events:
            key = str(payload["idempotency_key"])
            event = existing.get(key)
            if event is None:
                event = OutboxEvent(
                    event_type=payload["event_type"],
                    aggregate_type=payload["aggregate_type"],
                    aggregate_id=str(payload["aggregate_id"]),
                    idempotency_key=key,
                    payload=payload["payload"],
                    status="pending",
                )
                db.add(event)
                existing[key] = event
            result.append(event)
        await db.flush()
        return result

    async def enqueue(
        self,
        db: AsyncSession,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        idempotency_key: str,
        payload: dict,
    ) -> OutboxEvent:
        existing = await db.scalar(
            select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status="pending",
        )
        db.add(event)
        await db.flush()
        return event

    async def pending_ids(self, db: AsyncSession, *, limit: int = 100) -> list[int]:
        rows = await db.scalars(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status.in_(("pending", "failed", "processing")),
                OutboxEvent.available_at <= datetime.now(UTC),
            )
            .order_by(OutboxEvent.id)
            .limit(limit)
        )
        return [int(event_id) for event_id in rows.all()]

    async def get(
        self, db: AsyncSession, *, event_id: int, for_update: bool = False
    ) -> OutboxEvent | None:
        stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
        if for_update:
            stmt = stmt.with_for_update()
        return await db.scalar(stmt)

    async def begin(self, db: AsyncSession, *, event: OutboxEvent) -> bool:
        now = datetime.now(UTC)
        if event.status == "processing" and event.available_at > now:
            return False
        if event.status not in {"pending", "failed", "processing"}:
            return False
        event.status = "processing"
        event.attempts += 1
        event.last_error = None
        event.available_at = now + timedelta(seconds=90)
        await db.flush()
        return True

    async def published(self, db: AsyncSession, *, event: OutboxEvent) -> None:
        event.status = "published"
        event.published_at = datetime.now(UTC)
        event.last_error = None
        await db.flush()

    async def failed(self, db: AsyncSession, *, event: OutboxEvent, error: str) -> None:
        event.status = "failed"
        event.last_error = error[:512]
        delay_s = min(3600, 30 * (2 ** max(0, event.attempts - 1)))
        event.available_at = datetime.now(UTC) + timedelta(seconds=delay_s)
        await db.flush()

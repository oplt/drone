from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WebhookDelivery, WebhookEndpoint


class WebhookRepository:
    async def list_endpoints(
        self, db: AsyncSession, *, org_id: int, offset: int, limit: int
    ) -> list[WebhookEndpoint]:
        rows = await db.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.org_id == org_id)
            .order_by(WebhookEndpoint.created_at.desc(), WebhookEndpoint.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        return list(rows.all())

    async def create_endpoint(
        self,
        db: AsyncSession,
        *,
        org_id: int,
        user_id: int,
        url: str,
        events: list[str],
        secret: str,
    ) -> WebhookEndpoint:
        endpoint = WebhookEndpoint(
            org_id=org_id,
            url=url,
            events=events,
            secret=secret,
            is_active=True,
            created_by_user_id=user_id,
        )
        db.add(endpoint)
        await db.commit()
        await db.refresh(endpoint)
        return endpoint

    async def endpoint_for_org(
        self, db: AsyncSession, *, endpoint_id: int, org_id: int
    ) -> WebhookEndpoint | None:
        return await db.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.org_id == org_id,
            )
        )

    async def delete_endpoint_for_org(
        self, db: AsyncSession, *, endpoint_id: int, org_id: int
    ) -> bool:
        endpoint = await self.endpoint_for_org(db, endpoint_id=endpoint_id, org_id=org_id)
        if endpoint is None:
            return False
        await db.delete(endpoint)
        await db.commit()
        return True

    async def list_deliveries(
        self,
        db: AsyncSession,
        *,
        org_id: int,
        endpoint_id: int | None,
        offset: int,
        limit: int,
    ) -> list[WebhookDelivery]:
        stmt = (
            select(WebhookDelivery)
            .join(WebhookEndpoint, WebhookDelivery.endpoint_id == WebhookEndpoint.id)
            .where(WebhookEndpoint.org_id == org_id)
        )
        if endpoint_id is not None:
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
        rows = await db.scalars(
            stmt.order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        return list(rows.all())

    async def delivery_for_org(
        self, db: AsyncSession, *, delivery_id: int, org_id: int
    ) -> WebhookDelivery | None:
        return await db.scalar(
            select(WebhookDelivery)
            .join(WebhookEndpoint, WebhookDelivery.endpoint_id == WebhookEndpoint.id)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookEndpoint.org_id == org_id,
            )
        )

    async def subscribed_endpoints(
        self, db: AsyncSession, *, org_id: int, event_type: str
    ) -> list[WebhookEndpoint]:
        rows = await db.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.org_id == org_id,
                WebhookEndpoint.is_active.is_(True),
            )
        )
        return [endpoint for endpoint in rows.all() if event_type in (endpoint.events or [])]

    async def create_delivery_once(
        self,
        db: AsyncSession,
        *,
        endpoint_id: int,
        event_type: str,
        payload: dict,
        idempotency_key: str,
    ) -> tuple[WebhookDelivery, bool]:
        existing = await db.scalar(
            select(WebhookDelivery).where(WebhookDelivery.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False
        delivery = WebhookDelivery(
            endpoint_id=endpoint_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            idempotency_key=idempotency_key,
        )
        db.add(delivery)
        await db.flush()
        return delivery, True

    async def delivery_and_endpoint(
        self, db: AsyncSession, *, delivery_id: int, for_update: bool = False
    ) -> tuple[WebhookDelivery, WebhookEndpoint] | None:
        stmt = (
            select(WebhookDelivery, WebhookEndpoint)
            .join(WebhookEndpoint, WebhookDelivery.endpoint_id == WebhookEndpoint.id)
            .where(WebhookDelivery.id == delivery_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        row = await db.execute(stmt)
        pair = row.first()
        return (pair[0], pair[1]) if pair else None

    async def start_attempt(self, db: AsyncSession, *, delivery: WebhookDelivery) -> bool:
        if delivery.status == "processing" and delivery.last_attempted_at is not None:
            if delivery.last_attempted_at > datetime.now(UTC) - timedelta(seconds=90):
                return False
        elif delivery.status not in {"pending", "failed"}:
            return False
        delivery.status = "processing"
        delivery.attempts += 1
        delivery.last_attempted_at = datetime.now(UTC)
        delivery.error = None
        await db.flush()
        return True

    async def pending_ids(self, db: AsyncSession, *, limit: int = 100) -> list[int]:
        now = datetime.now(UTC)
        rows = await db.scalars(
            select(WebhookDelivery.id)
            .where(
                or_(
                    and_(
                        WebhookDelivery.status.in_(("pending", "failed")),
                        (WebhookDelivery.next_retry_at.is_(None))
                        | (WebhookDelivery.next_retry_at <= now),
                    ),
                    and_(
                        WebhookDelivery.status == "processing",
                        WebhookDelivery.last_attempted_at <= now - timedelta(seconds=90),
                    ),
                ),
            )
            .order_by(WebhookDelivery.id)
            .limit(limit)
        )
        return [int(delivery_id) for delivery_id in rows.all()]

    async def delivered(
        self, db: AsyncSession, *, delivery: WebhookDelivery, response_code: int
    ) -> None:
        delivery.status = "delivered"
        delivery.response_code = response_code
        delivery.next_retry_at = None
        delivery.error = None
        await db.flush()

    async def failed(
        self,
        db: AsyncSession,
        *,
        delivery: WebhookDelivery,
        error: str,
        response_code: int | None,
        retry_in_s: int | None,
    ) -> None:
        delivery.status = "failed"
        delivery.error = error[:500]
        delivery.response_code = response_code
        delivery.next_retry_at = (
            datetime.now(UTC) + timedelta(seconds=retry_in_s) if retry_in_s else None
        )
        await db.flush()

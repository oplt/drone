from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.alerts.models import AlertDelivery, OperationalAlert

ACTIVE_ALERT_STATUSES = ("open", "acknowledged")


class AlertRepository:
    async def get_active_alerts_for_rules(
        self, db: AsyncSession, *, rule_types: Sequence[str]
    ) -> list[OperationalAlert]:
        stmt = select(OperationalAlert).where(
            OperationalAlert.status.in_(ACTIVE_ALERT_STATUSES),
        )
        if rule_types:
            stmt = stmt.where(OperationalAlert.rule_type.in_(rule_types))
        return list((await db.execute(stmt)).scalars().all())

    async def create_alert(
        self,
        db: AsyncSession,
        *,
        rule_type: str,
        dedupe_key: str,
        source: str,
        severity: str,
        title: str,
        message: str,
        meta_data: dict[str, Any],
        now: datetime,
        org_id: int | None = None,
    ) -> OperationalAlert:
        alert = OperationalAlert(
            org_id=org_id,
            rule_type=rule_type,
            dedupe_key=dedupe_key,
            source=source,
            severity=severity,
            status="open",
            title=title,
            message=message,
            meta_data=meta_data,
            first_triggered_at=now,
            last_triggered_at=now,
            last_notified_at=now,
            occurrences=1,
        )
        db.add(alert)
        await db.flush()
        return alert

    async def touch_alert(
        self,
        db: AsyncSession,
        *,
        alert: OperationalAlert,
        severity: str,
        title: str,
        message: str,
        meta_data: dict[str, Any],
        now: datetime,
        mark_notified: bool,
    ) -> OperationalAlert:
        alert.severity = severity
        alert.title = title
        alert.message = message
        alert.meta_data = meta_data
        alert.last_triggered_at = now
        alert.occurrences = int(alert.occurrences or 0) + 1
        if mark_notified:
            alert.last_notified_at = now
        db.add(alert)
        await db.flush()
        return alert

    async def resolve_alert(
        self, db: AsyncSession, *, alert: OperationalAlert, now: datetime
    ) -> OperationalAlert:
        alert.status = "resolved"
        alert.resolved_at = now
        db.add(alert)
        await db.flush()
        return alert

    async def acknowledge_alert(
        self, db: AsyncSession, *, org_id: int, alert_id: int, user_id: int, now: datetime
    ) -> OperationalAlert | None:
        alert = await db.scalar(
            select(OperationalAlert).where(
                OperationalAlert.id == alert_id, OperationalAlert.org_id == org_id
            )
        )
        if not alert:
            return None
        if alert.status != "resolved":
            alert.status = "acknowledged"
            alert.acknowledged_at = now
            alert.acknowledged_by_user_id = user_id
            db.add(alert)
            await db.flush()
        return alert

    async def resolve_by_id(
        self, db: AsyncSession, *, org_id: int, alert_id: int, now: datetime
    ) -> OperationalAlert | None:
        alert = await db.scalar(
            select(OperationalAlert).where(
                OperationalAlert.id == alert_id, OperationalAlert.org_id == org_id
            )
        )
        if not alert:
            return None
        if alert.status != "resolved":
            alert.status = "resolved"
            alert.resolved_at = now
            db.add(alert)
            await db.flush()
        return alert

    async def record_delivery(
        self,
        db: AsyncSession,
        *,
        alert_id: int,
        channel: str,
        destination: str | None,
        status: str,
        payload: dict[str, Any] | None = None,
        provider_message_id: str | None = None,
        error: str | None = None,
        idempotency_key: str | None = None,
    ) -> AlertDelivery:
        if idempotency_key is not None:
            existing = await db.scalar(
                select(AlertDelivery).where(AlertDelivery.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return existing
        delivery = AlertDelivery(
            alert_id=alert_id,
            channel=channel,
            destination=destination,
            status=status,
            payload=payload or {},
            provider_message_id=provider_message_id,
            error=error,
            idempotency_key=idempotency_key,
        )
        db.add(delivery)
        await db.flush()
        return delivery

    async def list_alerts(
        self,
        db: AsyncSession,
        *,
        org_id: int,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OperationalAlert], int]:
        scope = OperationalAlert.org_id == org_id
        stmt = select(OperationalAlert).where(scope)
        count_stmt = select(func.count(OperationalAlert.id)).where(scope)
        normalized = (status or "active").lower().strip()
        if normalized in {"open", "resolved"}:
            predicate = OperationalAlert.status == normalized
            stmt, count_stmt = stmt.where(predicate), count_stmt.where(predicate)
        elif normalized != "all":
            predicate = OperationalAlert.status.in_(ACTIVE_ALERT_STATUSES)
            stmt, count_stmt = stmt.where(predicate), count_stmt.where(predicate)
        stmt = stmt.order_by(OperationalAlert.last_triggered_at.desc(), OperationalAlert.id.desc())
        stmt = stmt.limit(max(1, min(limit, 200))).offset(max(0, offset))
        rows = await db.execute(stmt)
        return list(rows.scalars().all()), int(await db.scalar(count_stmt) or 0)

    async def count_open_alerts(self, db: AsyncSession, *, org_id: int) -> int:
        total = await db.scalar(
            select(func.count(OperationalAlert.id)).where(
                OperationalAlert.org_id == org_id, OperationalAlert.status == "open"
            )
        )
        return int(total or 0)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

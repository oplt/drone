from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AlertDelivery, OperationalAlert

ACTIVE_ALERT_STATUSES = ("open", "acknowledged")


class AlertRepository:
    async def get_active_alerts_for_rules(
        self,
        db: AsyncSession,
        *,
        rule_types: Sequence[str],
    ) -> list[OperationalAlert]:
        stmt = select(OperationalAlert).where(
            OperationalAlert.status.in_(ACTIVE_ALERT_STATUSES),
        )
        if rule_types:
            stmt = stmt.where(OperationalAlert.rule_type.in_(rule_types))
        rows = await db.execute(stmt)
        return rows.scalars().all()

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
        meta_data: Dict[str, Any],
        now: datetime,
    ) -> OperationalAlert:
        alert = OperationalAlert(
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
        meta_data: Dict[str, Any],
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
        self,
        db: AsyncSession,
        *,
        alert: OperationalAlert,
        now: datetime,
    ) -> OperationalAlert:
        alert.status = "resolved"
        alert.resolved_at = now
        db.add(alert)
        await db.flush()
        return alert

    async def acknowledge_alert(
        self,
        db: AsyncSession,
        *,
        alert_id: int,
        user_id: int,
        now: datetime,
    ) -> OperationalAlert | None:
        row = await db.execute(select(OperationalAlert).where(OperationalAlert.id == alert_id))
        alert = row.scalar_one_or_none()
        if not alert:
            return None
        if alert.status == "resolved":
            return alert
        alert.status = "acknowledged"
        alert.acknowledged_at = now
        alert.acknowledged_by_user_id = user_id
        db.add(alert)
        await db.flush()
        return alert

    async def resolve_by_id(
        self,
        db: AsyncSession,
        *,
        alert_id: int,
        now: datetime,
    ) -> OperationalAlert | None:
        row = await db.execute(select(OperationalAlert).where(OperationalAlert.id == alert_id))
        alert = row.scalar_one_or_none()
        if not alert:
            return None
        if alert.status == "resolved":
            return alert
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
        payload: Dict[str, Any] | None = None,
        provider_message_id: str | None = None,
        error: str | None = None,
    ) -> AlertDelivery:
        row = AlertDelivery(
            alert_id=alert_id,
            channel=channel,
            destination=destination,
            status=status,
            payload=payload or {},
            provider_message_id=provider_message_id,
            error=error,
        )
        db.add(row)
        await db.flush()
        return row

    async def list_alerts(
        self,
        db: AsyncSession,
        *,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OperationalAlert], int]:
        stmt = select(OperationalAlert)
        count_stmt = select(func.count(OperationalAlert.id))

        normalized = (status or "active").lower().strip()
        if normalized == "open":
            predicate = OperationalAlert.status == "open"
            stmt = stmt.where(predicate)
            count_stmt = count_stmt.where(predicate)
        elif normalized == "resolved":
            predicate = OperationalAlert.status == "resolved"
            stmt = stmt.where(predicate)
            count_stmt = count_stmt.where(predicate)
        elif normalized == "all":
            pass
        else:
            predicate = OperationalAlert.status.in_(ACTIVE_ALERT_STATUSES)
            stmt = stmt.where(predicate)
            count_stmt = count_stmt.where(predicate)

        stmt = stmt.order_by(OperationalAlert.last_triggered_at.desc(), OperationalAlert.id.desc())
        stmt = stmt.limit(max(1, min(limit, 200))).offset(max(0, offset))

        rows = await db.execute(stmt)
        total = await db.scalar(count_stmt)
        return rows.scalars().all(), int(total or 0)

    async def count_open_alerts(self, db: AsyncSession) -> int:
        total = await db.scalar(
            select(func.count(OperationalAlert.id)).where(OperationalAlert.status == "open")
        )
        return int(total or 0)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)

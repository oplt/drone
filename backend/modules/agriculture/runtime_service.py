"""Reliable agriculture runtime event and replay primitives."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.models import AgricultureFlight, AgricultureRuntimeEvent


async def append_event(
    db: AsyncSession,
    *,
    flight_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    state: str | None = None,
    severity: str = "info",
    source: str = "agriculture.runtime",
) -> AgricultureRuntimeEvent:
    """Append the next event while locking the owning flight row."""
    await db.execute(select(AgricultureFlight.id).where(AgricultureFlight.id == flight_id).with_for_update())
    latest = await db.scalar(
        select(func.max(AgricultureRuntimeEvent.sequence)).where(AgricultureRuntimeEvent.flight_id == flight_id)
    )
    event = AgricultureRuntimeEvent(
        flight_id=flight_id,
        sequence=int(latest or 0) + 1,
        event_type=event_type,
        severity=severity,
        state=state,
        payload=payload or {},
        source=source,
        occurred_at=datetime.now(UTC),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def replay_events(
    db: AsyncSession,
    *,
    flight_id: str,
    after_sequence: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    latest = int(await db.scalar(select(func.max(AgricultureRuntimeEvent.sequence)).where(AgricultureRuntimeEvent.flight_id == flight_id)) or 0)
    rows = list((await db.scalars(
        select(AgricultureRuntimeEvent)
        .where(AgricultureRuntimeEvent.flight_id == flight_id, AgricultureRuntimeEvent.sequence > after_sequence)
        .order_by(AgricultureRuntimeEvent.sequence.asc())
        .limit(limit)
    )).all())
    first = rows[0].sequence if rows else None
    return {
        "events": rows,
        "latest_sequence": latest,
        "next_sequence": (rows[-1].sequence + 1) if rows else max(after_sequence + 1, latest + 1),
        "has_more": bool(rows and rows[-1].sequence < latest),
        "gap_detected": first is not None and first > after_sequence + 1,
    }

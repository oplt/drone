"""Shared helpers for staged storage object lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def reconcile_staged_storage_objects(
    db: AsyncSession,
    model: Any,
    *,
    older_than_minutes: int,
    staged_state: str = "staged",
    orphan_state: str = "orphan",
) -> int:
    """Mark stale staged storage rows as orphan and commit."""
    cutoff = datetime.now(UTC) - timedelta(minutes=max(1, older_than_minutes))
    rows = list(
        (
            await db.scalars(
                select(model).where(
                    model.state == staged_state,
                    model.created_at < cutoff,
                )
            )
        ).all()
    )
    for item in rows:
        item.state = orphan_state
    await db.commit()
    return len(rows)

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import Select, and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import Session
from backend.modules.workflow_events.models import WorkflowEvent


async def append_workflow_event(
    db: AsyncSession,
    *,
    domain: str,
    stream_id: str,
    subject_id: str,
    event_type: str,
    org_id: int | None,
    user_id: int | None,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> WorkflowEvent:
    """Append an event in the caller's transaction.

    The caller owns commit/rollback so state and its lifecycle event become
    visible atomically. Dedupe keys are reserved for naturally idempotent
    transitions such as one stage attempt completing.
    """

    if dedupe_key:
        existing = await db.scalar(
            select(WorkflowEvent).where(WorkflowEvent.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing
    event = WorkflowEvent(
        domain=domain,
        stream_id=stream_id,
        subject_id=subject_id,
        event_type=event_type,
        org_id=org_id,
        user_id=user_id,
        payload=payload or {},
        dedupe_key=dedupe_key,
    )
    if not dedupe_key:
        db.add(event)
        await db.flush()
        return event
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        # A concurrent delivery may reserve the same transition after the
        # optimistic read above. Roll back only the savepoint, then reuse it.
        existing = await db.scalar(
            select(WorkflowEvent).where(WorkflowEvent.dedupe_key == dedupe_key)
        )
        if existing is None:
            raise
        return existing
    return event


def _scope_clause(*, org_id: int | None, user_id: int) -> Any:
    if org_id is not None:
        return WorkflowEvent.org_id == org_id
    return and_(WorkflowEvent.org_id.is_(None), WorkflowEvent.user_id == user_id)


def _sse(event: WorkflowEvent) -> str:
    data = {
        "id": event.id,
        "domain": event.domain,
        "stream_id": event.stream_id,
        "subject_id": event.subject_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at.isoformat()
        if isinstance(event.created_at, datetime)
        else str(event.created_at),
    }
    return (
        f"id: {event.id}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"
    )


async def load_workflow_events(
    db: AsyncSession,
    *,
    domain: str,
    stream_id: str,
    org_id: int | None,
    user_id: int,
    after_id: int = 0,
    limit: int = 100,
) -> list[WorkflowEvent]:
    """Load one authorized replay page; scope is always part of the SQL query."""
    query = workflow_event_query(
        domain=domain,
        stream_id=stream_id,
        org_id=org_id,
        user_id=user_id,
        after_id=after_id,
        limit=limit,
    )
    return list((await db.scalars(query)).all())


def workflow_event_query(
    *,
    domain: str,
    stream_id: str,
    org_id: int | None,
    user_id: int,
    after_id: int = 0,
    limit: int = 100,
) -> Select[tuple[WorkflowEvent]]:
    """Build the mandatory scope-filtered replay query."""
    return (
        select(WorkflowEvent)
        .where(
            WorkflowEvent.domain == domain,
            WorkflowEvent.stream_id == stream_id,
            WorkflowEvent.id > max(0, after_id),
            _scope_clause(org_id=org_id, user_id=user_id),
        )
        .order_by(WorkflowEvent.id.asc())
        .limit(max(1, min(limit, 400)))
    )


async def workflow_event_stream(
    request: Request,
    *,
    domain: str,
    stream_id: str,
    org_id: int | None,
    user_id: int,
    after_id: int = 0,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Replay from a durable cursor, then tail with bounded DB polling.

    Native EventSource reconnects with ``Last-Event-ID``. Database polling is
    isolated to the HTTP stream and does not enqueue workflow jobs.
    """

    cursor = max(0, after_id)
    idle_seconds = 0.0
    yield "retry: 3000\n\n"
    while not await request.is_disconnected():
        async with Session() as db:
            rows = await load_workflow_events(
                db,
                domain=domain,
                stream_id=stream_id,
                org_id=org_id,
                user_id=user_id,
                after_id=cursor,
            )
        if rows:
            idle_seconds = 0.0
            for event in rows:
                cursor = int(event.id)
                yield _sse(event)
            continue
        await asyncio.sleep(poll_seconds)
        idle_seconds += poll_seconds
        if idle_seconds >= heartbeat_seconds:
            idle_seconds = 0.0
            yield ": heartbeat\n\n"

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureFlight
from backend.modules.workflow_events.service import append_workflow_event

ANALYSIS_EVENT_DOMAIN = "agriculture_analysis"


async def append_analysis_event(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
    event_type: str,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> None:
    await append_workflow_event(
        db,
        domain=ANALYSIS_EVENT_DOMAIN,
        stream_id=run.id,
        subject_id=run.id,
        event_type=event_type,
        org_id=flight.org_id,
        user_id=run.requested_by_user_id,
        payload={"run_id": run.id, "flight_id": flight.id, **(payload or {})},
        dedupe_key=dedupe_key,
    )


async def append_analysis_status_event(
    db: AsyncSession,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
    event_type: str,
    key: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a run-status event with the canonical status/progress envelope."""
    await append_analysis_event(
        db,
        run=run,
        flight=flight,
        event_type=event_type,
        payload={"status": run.status, "progress": run.progress, **(payload or {})},
        dedupe_key=f"analysis:{run.id}:{key}:a{run.retry_count}",
    )

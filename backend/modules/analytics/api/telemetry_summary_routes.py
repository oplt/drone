from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.database.session import Session
from backend.modules.analytics.api.analytics_route_deps import VALID_TELEMETRY_SUMMARY_RESOLUTIONS
from backend.modules.identity.dependencies import require_user
from backend.modules.telemetry.repository import TelemetryRepository

router = APIRouter(tags=["analytics"])


@router.get("/flights/{flight_id}/telemetry/summary")
async def flight_telemetry_summary(
    flight_id: int,
    resolution: int = Query(
        10,
        description="Bucket size in seconds. One of 1, 10, or 60.",
    ),
    _user=Depends(require_user),
) -> dict[str, Any]:
    """
    Return pre-aggregated telemetry buckets for a finished flight.

    Each bucket contains averaged altitude, groundspeed, and battery-remaining
    values at the requested resolution (1 s / 10 s / 60 s).  Data is read from
    the ``telemetry_summary`` table populated at flight-end by the orchestrator.
    """
    if resolution not in VALID_TELEMETRY_SUMMARY_RESOLUTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"resolution must be one of {sorted(VALID_TELEMETRY_SUMMARY_RESOLUTIONS)}",
        )

    repo = TelemetryRepository(Session)
    rows = await repo.get_telemetry_summary(flight_id, resolution)

    return {
        "flight_id": flight_id,
        "resolution_s": resolution,
        "buckets": [
            {
                "ts": row.bucket_ts.isoformat(),
                "avg_alt": row.avg_alt,
                "min_alt": row.min_alt,
                "max_alt": row.max_alt,
                "avg_groundspeed": row.avg_groundspeed,
                "avg_battery_remaining": row.avg_battery_remaining,
                "min_battery_remaining": row.min_battery_remaining,
                "sample_count": row.sample_count,
            }
            for row in rows
        ],
    }

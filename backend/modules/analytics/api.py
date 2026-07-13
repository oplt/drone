from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.core.database.session import Session, get_db
from backend.infrastructure.cache.redis import get_redis_client
from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.identity.dependencies import OrgUser, require_org_user, require_user
from backend.modules.missions.flight_models import Flight, FlightEvent
from backend.modules.telemetry.models import TelemetryRecord
from backend.modules.telemetry.repository import TelemetryRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalyticsSummary(BaseModel):
    active_flights: int
    flights_24h: int
    telemetry_24h: int
    flight_hours_7d: float
    avg_battery_24h: float | None


class AnalyticsTrends(BaseModel):
    days: list[str]
    flight_hours: list[float]
    flight_counts: list[int]
    telemetry_counts: list[int]


class AnalyticsCoveragePoint(BaseModel):
    label: str
    value: float


class AnalyticsRecentFlight(BaseModel):
    id: int
    name: str
    status: str
    started_at: str
    ended_at: str | None
    duration_min: float
    distance_km: float
    telemetry_points: int


class AnalyticsEvent(BaseModel):
    id: int
    flight_id: int
    type: str
    created_at: str
    data: dict[str, Any]


class AnalyticsSystem(BaseModel):
    telemetry_running: bool
    active_connections: int
    last_update: Any = None
    mavlink_connected: bool


class AnalyticsOverviewResponse(BaseModel):
    summary: AnalyticsSummary
    trends: AnalyticsTrends
    coverage: list[AnalyticsCoveragePoint]
    recent_flights: list[AnalyticsRecentFlight]
    events: list[AnalyticsEvent]
    system: AnalyticsSystem


def _date_key(dt: datetime) -> str:
    return dt.date().isoformat()


def _daterange(end: datetime, days: int) -> list[datetime]:
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Simple haversine for approximate distance.
    import math

    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))




@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def overview(
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    from backend.modules.analytics.cache import get_cached_overview, set_cached_overview

    org_id = org_user.org_id
    redis = get_redis_client()
    cached = await get_cached_overview(redis, org_id)
    if cached is not None:
        return cached

    flight_scope = Flight.org_id == org_id
    telemetry_scope = TelemetryRecord.flight_id.in_(
        select(Flight.id).where(flight_scope)
    )
    event_scope = FlightEvent.flight_id.in_(select(Flight.id).where(flight_scope))
    now = datetime.now(UTC)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    flight_summary = (
        await db.execute(
            select(
                func.count(case((Flight.ended_at.is_(None), 1))).label("active_flights"),
                func.count(case((Flight.started_at >= last_24h, 1))).label("flights_24h"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Flight.started_at >= last_7d,
                                func.extract(
                                    "epoch",
                                    func.coalesce(Flight.ended_at, now) - Flight.started_at,
                                ),
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("flight_seconds_7d"),
            ).where(flight_scope)
        )
    ).one()
    active_flights = flight_summary.active_flights
    flights_24h = flight_summary.flights_24h
    flights_last_7 = flight_summary.flight_seconds_7d
    flight_hours_7d = float(flights_last_7 or 0.0) / 3600.0

    telemetry_summary = (
        await db.execute(
            select(
                func.count(case((TelemetryRecord.created_at >= last_24h, 1))).label(
                    "telemetry_24h"
                ),
                func.avg(
                    case(
                        (
                            and_(
                                TelemetryRecord.created_at >= last_24h,
                                TelemetryRecord.battery_remaining.isnot(None),
                            ),
                            TelemetryRecord.battery_remaining,
                        )
                    )
                ).label("avg_battery_24h"),
            )
            .select_from(TelemetryRecord)
            .where(telemetry_scope)
        )
    ).one()
    telemetry_24h = telemetry_summary.telemetry_24h
    avg_battery_24h = telemetry_summary.avg_battery_24h

    day_bucket = func.date(Flight.started_at)
    flight_hour_rows = (
        await db.execute(
            select(
                day_bucket,
                func.count(),
                func.coalesce(
                    func.sum(
                        func.extract(
                            "epoch",
                            func.coalesce(Flight.ended_at, now) - Flight.started_at,
                        )
                    ),
                    0.0,
                ),
            )
            .where(flight_scope, Flight.started_at >= last_30d)
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
    ).all()

    # Build day buckets
    days = _daterange(now, 30)
    day_keys = [_date_key(d) for d in days]
    flight_hours_by_day = {k: 0.0 for k in day_keys}
    flight_counts_by_day = {k: 0 for k in day_keys}
    for day_value, count, seconds in flight_hour_rows:
        if day_value is None:
            continue
        key = str(day_value)
        if key not in flight_hours_by_day:
            continue
        flight_hours_by_day[key] = float(seconds or 0.0) / 3600.0
        flight_counts_by_day[key] = int(count or 0)

    # Telemetry counts by day
    day_bucket = func.date(TelemetryRecord.created_at)
    telemetry_rows = (
        await db.execute(
            select(day_bucket, func.count())
            .where(telemetry_scope, TelemetryRecord.created_at >= last_30d)
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
    ).all()
    telemetry_by_day = {k: 0 for k in day_keys}
    for day_value, count in telemetry_rows:
        if day_value is None:
            continue
        telemetry_by_day[str(day_value)] = int(count or 0)

    # Coverage distribution (quadrants relative to centroid). Keep this as a
    # database projection: the endpoint never materializes the 30-day flight set.
    centroid = (
        select(
            func.avg(Flight.start_lat).label("avg_lat"),
            func.avg(Flight.start_lon).label("avg_lon"),
        )
        .where(flight_scope, Flight.started_at >= last_30d)
        .cte("flight_centroid")
    )
    quadrant_row = (
        await db.execute(
            select(
                func.count(
                    case(
                        (
                            and_(
                                Flight.start_lat >= centroid.c.avg_lat,
                                Flight.start_lon >= centroid.c.avg_lon,
                            ),
                            1,
                        )
                    )
                ).label("north_east"),
                func.count(
                    case(
                        (
                            and_(
                                Flight.start_lat < centroid.c.avg_lat,
                                Flight.start_lon >= centroid.c.avg_lon,
                            ),
                            1,
                        )
                    )
                ).label("south_east"),
                func.count(
                    case(
                        (
                            and_(
                                Flight.start_lat < centroid.c.avg_lat,
                                Flight.start_lon < centroid.c.avg_lon,
                            ),
                            1,
                        )
                    )
                ).label("south_west"),
                func.count(
                    case(
                        (
                            and_(
                                Flight.start_lat >= centroid.c.avg_lat,
                                Flight.start_lon < centroid.c.avg_lon,
                            ),
                            1,
                        )
                    )
                ).label("north_west"),
            )
            .select_from(Flight)
            .join(centroid, true())
            .where(flight_scope, Flight.started_at >= last_30d)
        )
    ).one()
    quadrants = {
        "North East": int(quadrant_row.north_east or 0),
        "South East": int(quadrant_row.south_east or 0),
        "South West": int(quadrant_row.south_west or 0),
        "North West": int(quadrant_row.north_west or 0),
    }
    total = sum(quadrants.values())
    coverage = (
        [
            {"label": label, "value": round((count / total) * 100, 1)}
            for label, count in quadrants.items()
        ]
        if total
        else []
    )

    # Recent flights
    recent = (
        await db.execute(
            select(
                Flight.id,
                Flight.status,
                Flight.started_at,
                Flight.ended_at,
                Flight.start_lat,
                Flight.start_lon,
                Flight.dest_lat,
                Flight.dest_lon,
            )
            .where(flight_scope)
            .order_by(Flight.started_at.desc(), Flight.id.desc())
            .limit(12)
        )
    ).all()

    flight_ids = [int(f.id) for f in recent]
    telemetry_counts = {}
    if flight_ids:
        counts = (
            await db.execute(
                select(TelemetryRecord.flight_id, func.count())
                .where(telemetry_scope, TelemetryRecord.flight_id.in_(flight_ids))
                .group_by(TelemetryRecord.flight_id)
            )
        ).all()
        telemetry_counts = {fid: int(cnt) for fid, cnt in counts if fid is not None}

    recent_flights = []
    for f in recent:
        start = _ensure_aware(f.started_at)
        end = _ensure_aware(f.ended_at) if f.ended_at else now
        duration_min = max(0.0, (end - start).total_seconds() / 60)
        distance_km = _haversine_km(f.start_lat, f.start_lon, f.dest_lat, f.dest_lon)
        recent_flights.append(
            {
                "id": f.id,
                "name": f"Flight {f.id}",
                "status": f.status,
                "started_at": f.started_at.isoformat(),
                "ended_at": f.ended_at.isoformat() if f.ended_at else None,
                "duration_min": round(duration_min, 1),
                "distance_km": round(distance_km, 2),
                "telemetry_points": telemetry_counts.get(f.id, 0),
            }
        )

    # Recent events (best-effort)
    events = (
        (
            await db.execute(
                select(FlightEvent).where(event_scope).order_by(FlightEvent.created_at.desc()).limit(10)
            )
        )
        .scalars()
        .all()
    )
    recent_events = [
        {
            "id": e.id,
            "flight_id": e.flight_id,
            "type": e.type,
            "created_at": e.created_at.isoformat(),
            "data": e.data,
        }
        for e in events
    ]

    telemetry = telemetry_manager.runtime_snapshot()
    system = {
        "telemetry_running": telemetry["running"],
        "active_connections": telemetry["active_connections"],
        "last_update": telemetry["last_update"],
        "mavlink_connected": telemetry["source_connected"],
    }

    response = {
        "summary": {
            "active_flights": int(active_flights or 0),
            "flights_24h": int(flights_24h or 0),
            "telemetry_24h": int(telemetry_24h or 0),
            "flight_hours_7d": round(flight_hours_7d, 1),
            "avg_battery_24h": round(float(avg_battery_24h), 1)
            if avg_battery_24h is not None
            else None,
        },
        "trends": {
            "days": day_keys,
            "flight_hours": [round(flight_hours_by_day[k], 2) for k in day_keys],
            "flight_counts": [flight_counts_by_day[k] for k in day_keys],
            "telemetry_counts": [telemetry_by_day[k] for k in day_keys],
        },
        "coverage": coverage,
        "recent_flights": recent_flights,
        "events": recent_events,
        "system": system,
    }
    await set_cached_overview(
        redis,
        org_id,
        response,
        ttl=max(1, int(settings.analytics_cache_ttl_sec)),
    )
    return response


_VALID_RESOLUTIONS = {1, 10, 60}


@router.get("/flights/{flight_id}/telemetry/summary")
async def flight_telemetry_summary(
    flight_id: int,
    resolution: int = Query(
        10,
        description="Bucket size in seconds. One of 1, 10, or 60.",
    ),
    _user=Depends(require_user),
):
    """
    Return pre-aggregated telemetry buckets for a finished flight.

    Each bucket contains averaged altitude, groundspeed, and battery-remaining
    values at the requested resolution (1 s / 10 s / 60 s).  Data is read from
    the ``telemetry_summary`` table populated at flight-end by the orchestrator.
    """
    if resolution not in _VALID_RESOLUTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"resolution must be one of {sorted(_VALID_RESOLUTIONS)}",
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

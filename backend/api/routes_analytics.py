from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.deps import require_user
from backend.db.models import Flight, TelemetryRecord, FlightEvent
from backend.db.session import get_db
from backend.messaging.websocket import telemetry_manager


router = APIRouter(prefix="/analytics", tags=["analytics"])


def _date_key(dt: datetime) -> str:
    return dt.date().isoformat()


def _daterange(end: datetime, days: int) -> List[datetime]:
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Simple haversine for approximate distance.
    import math

    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_user),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    active_flights = await db.scalar(
        select(func.count()).select_from(Flight).where(Flight.ended_at.is_(None))
    )
    flights_24h = await db.scalar(
        select(func.count()).select_from(Flight).where(Flight.started_at >= last_24h)
    )
    telemetry_24h = await db.scalar(
        select(func.count())
        .select_from(TelemetryRecord)
        .where(TelemetryRecord.created_at >= last_24h)
    )
    avg_battery_24h = await db.scalar(
        select(func.avg(TelemetryRecord.battery_remaining))
        .select_from(TelemetryRecord)
        .where(
            TelemetryRecord.created_at >= last_24h,
            TelemetryRecord.battery_remaining.isnot(None),
        )
    )

    flights_last_7 = (
        await db.execute(select(Flight).where(Flight.started_at >= last_7d))
    ).scalars().all()
    flight_hours_7d = 0.0
    for f in flights_last_7:
        start = _ensure_aware(f.started_at)
        end = _ensure_aware(f.ended_at) if f.ended_at else now
        flight_hours_7d += (end - start).total_seconds() / 3600

    flights_last_30 = (
        await db.execute(select(Flight).where(Flight.started_at >= last_30d))
    ).scalars().all()

    # Build day buckets
    days = _daterange(now, 30)
    day_keys = [_date_key(d) for d in days]
    flight_hours_by_day = {k: 0.0 for k in day_keys}
    flight_counts_by_day = {k: 0 for k in day_keys}

    for f in flights_last_30:
        key = _date_key(_ensure_aware(f.started_at))
        if key not in flight_hours_by_day:
            continue
        start = _ensure_aware(f.started_at)
        end = _ensure_aware(f.ended_at) if f.ended_at else now
        flight_hours_by_day[key] += (end - start).total_seconds() / 3600
        flight_counts_by_day[key] += 1

    # Telemetry counts by day
    day_bucket = func.date(TelemetryRecord.created_at)
    telemetry_rows = (
        await db.execute(
            select(day_bucket, func.count())
            .where(TelemetryRecord.created_at >= last_30d)
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
    ).all()
    telemetry_by_day = {k: 0 for k in day_keys}
    for day_value, count in telemetry_rows:
        if day_value is None:
            continue
        telemetry_by_day[str(day_value)] = int(count or 0)

    # Coverage distribution (quadrants relative to centroid)
    coverage = []
    if flights_last_30:
        avg_lat = mean([f.start_lat for f in flights_last_30])
        avg_lon = mean([f.start_lon for f in flights_last_30])
        quadrants = {
            "North East": 0,
            "South East": 0,
            "South West": 0,
            "North West": 0,
        }
        for f in flights_last_30:
            north = f.start_lat >= avg_lat
            east = f.start_lon >= avg_lon
            if north and east:
                quadrants["North East"] += 1
            elif not north and east:
                quadrants["South East"] += 1
            elif not north and not east:
                quadrants["South West"] += 1
            else:
                quadrants["North West"] += 1

        total = max(1, sum(quadrants.values()))
        coverage = [
            {"label": label, "value": round((count / total) * 100, 1)}
            for label, count in quadrants.items()
        ]

    # Recent flights
    recent = (
        await db.execute(
            select(Flight).order_by(Flight.started_at.desc()).limit(12)
        )
    ).scalars().all()

    flight_ids = [f.id for f in recent]
    telemetry_counts = {}
    if flight_ids:
        counts = (
            await db.execute(
                select(TelemetryRecord.flight_id, func.count())
                .where(TelemetryRecord.flight_id.in_(flight_ids))
                .group_by(TelemetryRecord.flight_id)
            )
        ).all()
        telemetry_counts = {fid: int(cnt) for fid, cnt in counts if fid is not None}

    recent_flights = []
    for f in recent:
        start = _ensure_aware(f.started_at)
        end = _ensure_aware(f.ended_at) if f.ended_at else now
        duration_min = max(0.0, (end - start).total_seconds() / 60)
        distance_km = _haversine_km(
            f.start_lat, f.start_lon, f.dest_lat, f.dest_lon
        )
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
        await db.execute(
            select(FlightEvent)
            .order_by(FlightEvent.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
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

    system = {
        "telemetry_running": telemetry_manager._running,
        "active_connections": len(telemetry_manager.active_connections),
        "last_update": telemetry_manager.last_telemetry.get("timestamp", 0),
        "mavlink_connected": telemetry_manager.mav_conn is not None,
    }

    return {
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

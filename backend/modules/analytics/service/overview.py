from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.messaging.websocket_publisher import telemetry_manager
from backend.modules.analytics.overview_helpers import (
    date_key,
    daterange,
    ensure_aware,
    haversine_km,
)
from backend.modules.missions.flight_models import Flight, FlightEvent
from backend.modules.telemetry.models import TelemetryRecord


async def build_analytics_overview(db: AsyncSession, org_id: int) -> dict[str, Any]:
    flight_scope = Flight.org_id == org_id
    telemetry_scope = TelemetryRecord.flight_id.in_(select(Flight.id).where(flight_scope))
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

    days = daterange(now, 30)
    day_keys = [date_key(d) for d in days]
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
    telemetry_counts: dict[int, int] = {}
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
        start = ensure_aware(f.started_at)
        end = ensure_aware(f.ended_at) if f.ended_at else now
        duration_min = max(0.0, (end - start).total_seconds() / 60)
        distance_km = haversine_km(f.start_lat, f.start_lon, f.dest_lat, f.dest_lon)
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

    events = (
        (
            await db.execute(
                select(FlightEvent)
                .where(event_scope)
                .order_by(FlightEvent.created_at.desc())
                .limit(10)
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

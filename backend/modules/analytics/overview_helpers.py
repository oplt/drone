from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta


def date_key(dt: datetime) -> str:
    return dt.date().isoformat()


def daterange(end: datetime, days: int) -> list[datetime]:
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

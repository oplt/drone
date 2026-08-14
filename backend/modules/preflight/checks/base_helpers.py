from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from .schemas import CheckResult, CheckStatus


class PreflightCheckHelpers:
    """Shared assertion and geometry helpers for baseline preflight checks."""

    def _ok(self, name: str, message: str | None = None) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.PASS, message=message)

    def _fail(self, name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.FAIL, message=message)

    def _warn(self, name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.WARN, message=message)

    def _skip(self, name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status=CheckStatus.SKIP, message=message)

    @staticmethod
    def _as_latlon(point: Any) -> tuple[float, float] | None:
        """Best-effort extraction of (lat, lon) from tuples/dicts/objects."""
        try:
            if isinstance(point, (tuple, list)) and len(point) >= 2:
                return float(point[0]), float(point[1])
            if isinstance(point, dict) and "lat" in point and "lon" in point:
                return float(point["lat"]), float(point["lon"])
            if hasattr(point, "lat") and hasattr(point, "lon"):
                return float(point.lat), float(point.lon)
            if hasattr(point, "latitude") and hasattr(point, "longitude"):
                return float(point.latitude), float(point.longitude)
        except Exception:
            return None
        return None

    def _normalize_polygon(self, polygon: Iterable[Any]) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for p in polygon:
            ll = self._as_latlon(p)
            if ll is not None:
                pts.append(ll)
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts.pop()
        return pts

    @staticmethod
    def _point_in_polygon(lat: float, lon: float, polygon: Sequence[tuple[float, float]]) -> bool:
        """Ray-casting point-in-polygon using lat/lon as local planar coordinates."""
        if len(polygon) < 3:
            return False
        x = lon
        y = lat
        inside = False
        n = len(polygon)
        for i in range(n):
            y1, x1 = polygon[i]
            y2, x2 = polygon[(i + 1) % n]
            intersects = ((y1 > y) != (y2 > y)) and (
                x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-16) + x1
            )
            if intersects:
                inside = not inside
        return inside

    @staticmethod
    def _dedupe_by_name(results: list[CheckResult]) -> list[CheckResult]:
        seen = set()
        out: list[CheckResult] = []
        for r in results:
            if getattr(r, "name", None) in seen:
                continue
            seen.add(r.name)
            out.append(r)
        return out

    @staticmethod
    def _has_fail(results: list[CheckResult]) -> bool:
        return any(r.status == CheckStatus.FAIL for r in results)

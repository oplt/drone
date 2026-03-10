from __future__ import annotations

from dataclasses import dataclass

from backend.ml.patrol.models import GeoPoint

try:
    from shapely.geometry import Point, Polygon
    from shapely.strtree import STRtree
except Exception:  # pragma: no cover - optional dependency
    Point = None
    Polygon = None
    STRtree = None


@dataclass
class Zone:
    name: str
    polygon: list[tuple[float, float]]
    restricted: bool = True


def point_in_polygon(point: GeoPoint, polygon: list[tuple[float, float]]) -> bool:
    x, y = point.lat, point.lon
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < ((x2 - x1) * (y - y1)) / ((y2 - y1) + 1e-9) + x1):
            inside = not inside
    return inside


class ZoneEngine:
    def __init__(self, zones: list[Zone] | None = None):
        self.zones = list(zones or [])
        self._strtree = None
        self._rebuild_index()

    def set_zones(self, zones: list[Zone]) -> None:
        self.zones = list(zones)
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        if Polygon is None or STRtree is None or not self.zones:
            self._strtree = None
            return
        polygons = [Polygon(zone.polygon) for zone in self.zones]
        self._strtree = STRtree(polygons)

    def find_zone_hits(self, point: GeoPoint) -> list[Zone]:
        if self._strtree is not None and Point is not None:
            matches = self._strtree.query(Point(point.lat, point.lon))
            return [self.zones[int(idx)] for idx in matches if point_in_polygon(point, self.zones[int(idx)].polygon)]
        return [z for z in self.zones if point_in_polygon(point, z.polygon)]

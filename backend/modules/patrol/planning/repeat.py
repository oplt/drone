from __future__ import annotations

from collections.abc import Sequence

from backend.modules.patrol.planning.geometry import coords_close
from backend.modules.vehicle_runtime.types import Coordinate


def repeat_patrol_loops(waypoints: Sequence[Coordinate], loops: int) -> list[Coordinate]:
    if not waypoints:
        return []

    loop_count = max(1, int(loops))
    closed = len(waypoints) >= 2 and coords_close(waypoints[0], waypoints[-1])
    base = list(waypoints[:-1] if closed else waypoints)
    if not base:
        return list(waypoints)

    out: list[Coordinate] = []
    for i in range(loop_count):
        segment = list(base)
        if i > 0 and out and segment and coords_close(out[-1], segment[0]):
            segment = segment[1:]
        out.extend(segment)

    if len(out) >= 2 and not coords_close(out[0], out[-1]):
        first = out[0]
        out.append(Coordinate(lat=first.lat, lon=first.lon, alt=first.alt))

    return out

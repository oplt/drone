from __future__ import annotations

from shapely.affinity import rotate as rotate_geometry
from shapely.geometry import LineString, Polygon

from backend.modules.warehouse.planning.local_planner.geometry import (
    _collect_lines,
    _heading_deg,
    _normalize_angle_deg,
)
from backend.modules.warehouse.planning.local_planner.segment_geometry import (
    _clip_segment_endpoints,
)
from backend.modules.warehouse.planning.local_planner.models import (
    WarehouseCorridor,
    WarehouseLocalPoint,
)

def _generate_corridors_for_axis(
    *,
    flyable_polygon: Polygon,
    axis_deg: float,
    corridor_spacing_m: float,
    clearance_m: float,
    width_m: float,
    source: str,
) -> list[WarehouseCorridor]:
    rotated = rotate_geometry(flyable_polygon, -axis_deg, origin=(0, 0))
    minx, miny, maxx, maxy = rotated.bounds
    height = maxy - miny
    if height <= 0:
        return []

    sweep_positions: list[float] = []
    usable_spacing = max(corridor_spacing_m, clearance_m * 2.0, 0.5)
    if height <= usable_spacing:
        sweep_positions = [(miny + maxy) * 0.5]
    else:
        cursor = miny + usable_spacing * 0.5
        while cursor <= maxy - usable_spacing * 0.5 + 1e-6:
            sweep_positions.append(cursor)
            cursor += usable_spacing
        if not sweep_positions:
            sweep_positions = [(miny + maxy) * 0.5]

    corridors: list[WarehouseCorridor] = []
    for idx, y_pos in enumerate(sweep_positions):
        sweep_line = LineString(
            [
                (minx - usable_spacing * 2.0, y_pos),
                (maxx + usable_spacing * 2.0, y_pos),
            ]
        )
        clipped = rotated.intersection(sweep_line)
        for part_index, line in enumerate(_collect_lines(clipped)):
            coords = list(line.coords)
            if len(coords) < 2:
                continue
            start_xy, end_xy = coords[0], coords[-1]
            clipped_xy = _clip_segment_endpoints(
                start_xy=(float(start_xy[0]), float(start_xy[1])),
                end_xy=(float(end_xy[0]), float(end_xy[1])),
                trim_m=max(clearance_m, 0.0),
            )
            if clipped_xy is None:
                continue
            local_line = rotate_geometry(
                LineString([clipped_xy[0], clipped_xy[1]]),
                axis_deg,
                origin=(0, 0),
            )
            local_start_xy, local_end_xy = list(local_line.coords)
            heading = _normalize_angle_deg(_heading_deg(local_start_xy, local_end_xy))
            corridors.append(
                WarehouseCorridor(
                    corridor_id=f"{source}_{len(corridors)}_{idx}_{part_index}",
                    start=WarehouseLocalPoint(
                        x_m=float(local_start_xy[0]),
                        y_m=float(local_start_xy[1]),
                        z_m=0.0,
                    ),
                    end=WarehouseLocalPoint(
                        x_m=float(local_end_xy[0]),
                        y_m=float(local_end_xy[1]),
                        z_m=0.0,
                    ),
                    width_m=float(width_m),
                    heading_deg=heading,
                    axis_deg=_normalize_angle_deg(axis_deg),
                    source=source,
                    sort_key=float(y_pos),
                )
            )
    return corridors

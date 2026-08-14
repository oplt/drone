"""Compatibility re-export; geometry helpers live in planning.geometry."""

from backend.modules.patrol.planning.geometry import (
    coords_close as _coords_close,
)
from backend.modules.patrol.planning.geometry import (
    densify_ring_xy as _densify_ring_xy,
)
from backend.modules.patrol.planning.geometry import (
    dynamic_trigger_profile as _dynamic_trigger_profile,
)
from backend.modules.patrol.planning.geometry import (
    ensure_closed_ring as _ensure_closed_ring,
)
from backend.modules.patrol.planning.geometry import (
    is_clockwise_xy as _is_clockwise_xy,
)
from backend.modules.patrol.planning.geometry import (
    largest_polygon as _largest_polygon,
)
from backend.modules.patrol.planning.geometry import (
    largest_viable_inward_offset as _largest_viable_inward_offset,
)
from backend.modules.patrol.planning.geometry import (
    poly_centroid_lonlat as _poly_centroid_lonlat,
)
from backend.modules.patrol.planning.geometry import (
    polyline_length_m as _polyline_length_m,
)
from backend.modules.patrol.planning.geometry import (
    ring_signed_area_xy as _ring_signed_area_xy,
)
from backend.modules.patrol.planning.geometry import (
    route_length_for_coords as _route_length_for_coords,
)

__all__ = [
    "_coords_close",
    "_densify_ring_xy",
    "_dynamic_trigger_profile",
    "_ensure_closed_ring",
    "_is_clockwise_xy",
    "_largest_polygon",
    "_largest_viable_inward_offset",
    "_poly_centroid_lonlat",
    "_polyline_length_m",
    "_ring_signed_area_xy",
    "_route_length_for_coords",
]

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from shapely.affinity import rotate as rotate_geometry
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points

from backend.core.geometry.algorithm_runtime import (
    GEOMETRY_ALGORITHM_VERSION,
    geometry_plan_cache,
    workload_label,
)

WarehouseScanPattern = Literal[
    "aisle_serpentine",
    "stacked_passes",
    "crosshatch",
    "perimeter_aisle_hybrid",
]
WarehouseLaneStrategy = Literal["serpentine", "one_way"]
WarehouseViewMode = Literal["forward", "left_face", "right_face", "dual_face"]

from __future__ import annotations

from backend.modules.warehouse.planning.indoor import SimulatedSLAMProvider


class WarehousePerceptionSLAMProvider(SimulatedSLAMProvider):
    """Fallback SLAM provider backed by the existing indoor simulation model."""


from backend.modules.warehouse.repository.docks import WarehouseDockMixin
from backend.modules.warehouse.repository.jobs import WarehouseJobMixin, WarehouseModelVersionEntry
from backend.modules.warehouse.repository.maps import WarehouseMapMixin, WarehouseRepositoryError
from backend.modules.warehouse.repository.sensor_rigs import WarehouseSensorRigMixin


class WarehouseMappingRepository(
    WarehouseMapMixin, WarehouseDockMixin, WarehouseJobMixin, WarehouseSensorRigMixin
):
    pass


__all__ = ["WarehouseMappingRepository", "WarehouseModelVersionEntry", "WarehouseRepositoryError"]

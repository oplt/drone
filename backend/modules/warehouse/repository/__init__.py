from backend.modules.warehouse.repository.docks import WarehouseDockMixin
from backend.modules.warehouse.repository.jobs import WarehouseJobMixin, WarehouseModelVersionEntry
from backend.modules.warehouse.repository.maps import WarehouseMapMixin, WarehouseRepositoryError


class WarehouseMappingRepository(WarehouseMapMixin, WarehouseDockMixin, WarehouseJobMixin):
    pass


__all__ = ["WarehouseMappingRepository", "WarehouseModelVersionEntry", "WarehouseRepositoryError"]

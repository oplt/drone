from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class WarehouseRepositoryError(RuntimeError):
    pass


@dataclass(slots=True)
class WarehouseModelVersionEntry:
    id: int
    version: int
    status: str
    created_at: datetime

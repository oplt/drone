from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class OperationalAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_type: str
    dedupe_key: str
    source: str
    severity: str
    status: str
    title: str
    message: str
    meta_data: Dict[str, Any]
    first_triggered_at: datetime
    last_triggered_at: datetime
    last_notified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_user_id: Optional[int] = None
    occurrences: int
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    items: List[OperationalAlertOut]
    total: int


class AlertCountResponse(BaseModel):
    open_count: int

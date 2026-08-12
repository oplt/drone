from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class EvidenceRef(BaseModel):
    type: Literal["detection_crop"] = "detection_crop"
    source_entity_id: str
    frame_index: int
    timestamp: float
    storage_object_id: str
    checksum: str
    availability: Literal["available", "missing", "deleted"]
    spatial: dict[str, float] | None = None
    provenance: dict[str, Any]


class EvidenceResolverOut(BaseModel):
    detection_id: str
    evidence: EvidenceRef | None
    evidence_url: str | None
    evidence_path: None = None
    resolved_at: datetime

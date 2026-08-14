from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

ZoneName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
ZoneCategory = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
ReviewNote = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class InterventionZoneCreateIn(BaseModel):
    name: ZoneName
    category: ZoneCategory
    source_observation_ids: list[str] = Field(..., min_length=1, max_length=100)


class InterventionZoneUpdateIn(BaseModel):
    expected_revision: int = Field(..., ge=1)
    name: ZoneName | None = None
    category: ZoneCategory | None = None
    geometry_geojson: dict[str, Any] | None = None


class InterventionZoneApprovalIn(BaseModel):
    status: Literal["approved", "rejected"]
    note: ReviewNote
    expected_revision: int = Field(..., ge=1)


class InterventionZoneOut(BaseModel):
    id: str
    org_id: int | None = None
    field_id: int
    flight_id: str
    run_id: str
    name: str
    category: str
    geometry_geojson: dict[str, Any]
    area_m2: float
    source_observation_ids: list[Any]
    evidence_ids: list[Any]
    model_versions: list[Any]
    status: str
    revision: int
    created_by_user_id: int | None = None
    reviewed_by_user_id: int | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

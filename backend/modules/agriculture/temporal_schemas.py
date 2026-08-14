"""HTTP response contracts for repeat-flight change intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgricultureChangeOut(BaseModel):
    id: str
    field_id: int
    current_flight_id: str
    reference_flight_id: str
    current_observation_id: str | None = None
    previous_observation_id: str | None = None
    observation_type: str
    state: str
    geometry_geojson: dict[str, Any]
    reference_geometry_geojson: dict[str, Any]
    area_m2: float | None = None
    delta_area_m2: float | None = None
    delta_intensity: float | None = None
    confidence: float
    evidence_ids: list[Any]
    uncertainty: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AgricultureComparisonOut(BaseModel):
    id: str | None = None
    status: str
    current_flight_id: str
    reference_flight_id: str | None = None
    alignment: dict[str, Any] = Field(default_factory=dict)
    comparability: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    changes: list[AgricultureChangeOut] = Field(default_factory=list)
    source_runs: dict[str, str] = Field(default_factory=dict)
    methodology: dict[str, Any] = Field(default_factory=dict)

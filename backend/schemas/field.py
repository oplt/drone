# backend/schemas/field.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

LonLat = list[float]  # [lon, lat]


class FieldCreateGeoJSON(BaseModel):
    """
    GeoJSON-style polygon ring:
      coordinates = [[lon,lat], [lon,lat], ...]
    Ring can be open or closed; backend will close it.
    """

    name: str = Field(..., min_length=1, max_length=128)
    coordinates: list[LonLat]
    owner_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FieldUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    coordinates: list[LonLat] | None = None
    metadata: dict[str, Any] | None = None


class FieldOut(BaseModel):
    id: int
    owner_id: int | None = None
    name: str
    area_ha: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True

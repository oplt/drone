# backend/schemas/field.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


LonLat = List[float]  # [lon, lat]


class FieldCreateGeoJSON(BaseModel):
    """
    GeoJSON-style polygon ring:
      coordinates = [[lon,lat], [lon,lat], ...]
    Ring can be open or closed; backend will close it.
    """
    name: str = Field(..., min_length=1, max_length=128)
    coordinates: List[LonLat]
    owner_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FieldUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    coordinates: Optional[List[LonLat]] = None
    metadata: Optional[Dict[str, Any]] = None


class FieldOut(BaseModel):
    id: int
    owner_id: Optional[int] = None
    name: str
    area_ha: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
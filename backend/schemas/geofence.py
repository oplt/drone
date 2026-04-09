from typing import Any

from pydantic import BaseModel, Field


class GeofenceCreateGeoJSON(BaseModel):
    """
    GeoJSON-style polygon ring, usually [lon, lat].
    Expecting a SINGLE outer ring (no holes) for now:
      coordinates = [[lon,lat], [lon,lat], ...]  (ring can be open or closed)
    """

    name: str = Field(..., min_length=1, max_length=128)
    coordinates: list[list[float]]  # [[lon, lat], ...]
    min_alt_m: float | None = None
    max_alt_m: float | None = None
    source: str | None = "geojson_upload"
    source_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class GeofenceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    coordinates: list[list[float]] | None = None
    min_alt_m: float | None = None
    max_alt_m: float | None = None
    source: str | None = None
    source_ref: str | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class GeofenceOut(BaseModel):
    id: int
    name: str
    min_alt_m: float | None = None
    max_alt_m: float | None = None
    is_active: bool
    source: str | None = None
    source_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class GeofenceCreateGeoJSON(BaseModel):
    """
    GeoJSON-style polygon ring, usually [lon, lat].
    Expecting a SINGLE outer ring (no holes) for now:
      coordinates = [[lon,lat], [lon,lat], ...]  (ring can be open or closed)
    """
    name: str = Field(..., min_length=1, max_length=128)
    coordinates: List[List[float]]  # [[lon, lat], ...]
    min_alt_m: Optional[float] = None
    max_alt_m: Optional[float] = None
    source: Optional[str] = "geojson_upload"
    source_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class GeofenceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    coordinates: Optional[List[List[float]]] = None
    min_alt_m: Optional[float] = None
    max_alt_m: Optional[float] = None
    source: Optional[str] = None
    source_ref: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class GeofenceOut(BaseModel):
    id: int
    name: str
    min_alt_m: Optional[float] = None
    max_alt_m: Optional[float] = None
    is_active: bool
    source: Optional[str] = None
    source_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
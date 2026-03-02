# backend/schemas/livestock.py
from __future__ import annotations

from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class HerdCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    pasture_geofence_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HerdOut(BaseModel):
    id: int
    name: str
    pasture_geofence_id: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class AnimalCreate(BaseModel):
    herd_id: int
    collar_id: str = Field(..., min_length=1, max_length=128)
    name: Optional[str] = Field(None, max_length=128)
    species: Literal["cow", "sheep", "goat"] = "cow"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnimalOut(BaseModel):
    id: int
    herd_id: int
    collar_id: str
    name: Optional[str] = None
    species: str
    is_active: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class AnimalPositionIn(BaseModel):
    """
    What your collar gateway would POST.
    """
    collar_id: str
    lat: float
    lon: float
    alt: Optional[float] = None
    speed_mps: Optional[float] = None
    activity: Optional[float] = None
    source: str = "collar"
    raw: Dict[str, Any] = Field(default_factory=dict)


class AnimalPositionOut(BaseModel):
    id: int
    animal_id: int
    created_at: datetime
    lat: float
    lon: float
    alt: Optional[float] = None
    speed_mps: Optional[float] = None
    activity: Optional[float] = None
    source: str
    raw: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class HerdTaskCreate(BaseModel):
    herd_id: int
    type: Literal["census", "herd_sweep", "search_locate"]  # expand later
    params: Dict[str, Any] = Field(default_factory=dict)


class HerdTaskOut(BaseModel):
    id: int
    herd_id: int
    type: str
    status: str
    flight_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    params: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class MissionPlanOut(BaseModel):
    """
    This is intentionally compatible with your mission schema style:
    type="route" + waypoints[] and optional speed/altitude_agl fields.
    """
    mission: Dict[str, Any]
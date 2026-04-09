# backend/schemas/livestock.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HerdCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    pasture_geofence_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HerdOut(BaseModel):
    id: int
    name: str
    pasture_geofence_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class AnimalCreate(BaseModel):
    herd_id: int
    collar_id: str = Field(..., min_length=1, max_length=128)
    name: str | None = Field(None, max_length=128)
    species: Literal["cow", "sheep", "goat"] = "cow"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnimalOut(BaseModel):
    id: int
    herd_id: int
    collar_id: str
    name: str | None = None
    species: str
    is_active: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
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
    alt: float | None = None
    speed_mps: float | None = None
    activity: float | None = None
    source: str = "collar"
    raw: dict[str, Any] = Field(default_factory=dict)


class AnimalPositionOut(BaseModel):
    id: int
    animal_id: int
    created_at: datetime
    lat: float
    lon: float
    alt: float | None = None
    speed_mps: float | None = None
    activity: float | None = None
    source: str
    raw: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class HerdTaskCreate(BaseModel):
    herd_id: int
    type: Literal["census", "herd_sweep", "search_locate"]  # expand later
    params: dict[str, Any] = Field(default_factory=dict)


class HerdTaskOut(BaseModel):
    id: int
    herd_id: int
    type: str
    status: str
    flight_id: int | None = None
    created_at: datetime
    updated_at: datetime
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class MissionPlanOut(BaseModel):
    """
    This is intentionally compatible with your mission schema style:
    type="route" + waypoints[] and optional speed/altitude_agl fields.
    """

    mission: dict[str, Any]

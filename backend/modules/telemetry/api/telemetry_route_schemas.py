from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.modules.missions.flight_profile import FlightEnvironment
from backend.modules.missions.schemas.mission_types import MissionType


class TelemetryConnectIn(BaseModel):
    mission_type: MissionType | None = None
    flight_environment: FlightEnvironment | None = None


ManualFlightCommand = Literal[
    "forward",
    "backward",
    "left",
    "right",
    "yaw_left",
    "yaw_right",
    "up",
    "down",
    "hold",
    "takeoff",
    "land",
]

ManualCommandPhase = Literal["start", "hold", "stop"]


class ManualControlIn(BaseModel):
    command: ManualFlightCommand
    phase: ManualCommandPhase = "start"
    source: str = Field(default="keyboard", max_length=32)
    flight_id: str | None = None

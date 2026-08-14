"""Warehouse coordinate-frame routes — request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.modules.warehouse.service.drift_guard import validate_localization_evidence

from .deps import validate_transform


class Translation3D(BaseModel):
    x: float
    y: float
    z: float


class UnitQuaternion(BaseModel):
    x: float
    y: float
    z: float
    w: float


class RigidTransform(BaseModel):
    translation: Translation3D
    rotation: UnitQuaternion


class CoordinateFrameCreate(BaseModel):
    transform: RigidTransform
    source: str = Field(..., min_length=1, max_length=64)
    confidence: float = Field(..., ge=0.0, le=1.0)
    covariance: list[float] = Field(default_factory=list, max_length=36)
    transform_timestamp: datetime
    max_age_s: float = Field(default=300.0, gt=0.0, le=86_400.0)
    localization_method: str = Field(..., min_length=1, max_length=64)
    commissioning_evidence: dict[str, Any] = Field(default_factory=dict)
    lock: bool = False

    @field_validator("transform")
    @classmethod
    def valid_transform(cls, value: RigidTransform) -> RigidTransform:
        validate_transform(value.model_dump())
        return value

    @field_validator("covariance")
    @classmethod
    def valid_covariance(cls, value: list[float]) -> list[float]:
        if value and len(value) != 36:
            raise ValueError("covariance must be empty or a row-major 6x6 matrix")
        return value

    @model_validator(mode="after")
    def valid_locked_evidence(self) -> CoordinateFrameCreate:
        if self.lock:
            validate_localization_evidence(
                transform=self.transform.model_dump(),
                transform_timestamp=self.transform_timestamp,
                max_age_s=self.max_age_s,
                covariance=self.covariance,
                confidence=self.confidence,
            )
        return self


class CoordinateFrameOut(BaseModel):
    id: int
    warehouse_map_id: int
    version: int
    parent_frame_id: str
    child_frame_id: str
    units: Literal["m"]
    axis_convention: Literal["ENU"]
    handedness: Literal["right"]
    transform: RigidTransform
    source: str
    status: Literal["draft", "locked", "superseded"]
    confidence: float | None
    covariance: list[float]
    transform_timestamp: datetime
    max_age_s: float
    localization_method: str
    transform_checksum: str
    meta_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    locked_at: datetime | None
    superseded_at: datetime | None


class CoordinateFrameValidationOut(BaseModel):
    valid: bool
    validation_warnings: list[dict[str, str]] = Field(default_factory=list)
    checksum_sha256: str
    commissioning_report: dict[str, Any] = Field(default_factory=dict)


class CoordinateDiagnosticsOut(BaseModel):
    warehouse_map_id: int
    generated_at: str
    mission_ready: bool
    coordinate_frame: dict | None
    latest_coordinate_frame: dict | None
    layout_version: dict | None
    latest_layout_version: dict | None
    localization_evidence: dict | None
    entity_counts: dict[str, int]
    frame_contract_checksum: str | None
    ros_map_odom_tf: dict | None = None
    ros_tf_tree: dict | None = None
    slam_localization: dict | None = None
    provisional_epoch: dict | None = None
    blocking_issues: list[dict[str, str]]
    warnings: list[dict[str, str]]


__all__ = [
    "CoordinateDiagnosticsOut",
    "CoordinateFrameCreate",
    "CoordinateFrameOut",
    "CoordinateFrameValidationOut",
    "RigidTransform",
    "Translation3D",
    "UnitQuaternion",
]

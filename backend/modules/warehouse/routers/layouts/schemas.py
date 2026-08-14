"""Warehouse layout routes — request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.core.pagination import Page


class LayoutEntityPage(Page[dict[str, Any]]):
    revision: int


class LayoutEntityIn(BaseModel):
    parent_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=64)
    level: int | None = None
    kind: str | None = None
    geometry: dict = Field(default_factory=dict)
    template_id: int | None = None
    template_version_id: int | None = None
    source_artifact_set_id: int | None = None
    fitted_transform_json: dict = Field(default_factory=dict)
    template_fit_json: dict = Field(default_factory=dict)
    face_plane_json: dict = Field(default_factory=dict)
    center_local_json: dict = Field(default_factory=dict)
    volume_json: dict = Field(default_factory=dict)
    confidence_breakdown_json: dict = Field(default_factory=dict)
    fit_residual_m: float | None = None
    observed_point_count: int | None = None
    coverage_ratio: float | None = None
    last_verified_at: datetime | None = None
    min_z_m: float | None = None
    max_z_m: float | None = None
    active: bool = True
    revision: int | None = None


class LayoutEntityPatch(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    level: int | None = None
    kind: str | None = None
    geometry: dict | None = None
    template_id: int | None = None
    template_version_id: int | None = None
    source_artifact_set_id: int | None = None
    fitted_transform_json: dict | None = None
    template_fit_json: dict | None = None
    face_plane_json: dict | None = None
    center_local_json: dict | None = None
    volume_json: dict | None = None
    confidence_breakdown_json: dict | None = None
    fit_residual_m: float | None = None
    observed_point_count: int | None = None
    coverage_ratio: float | None = None
    last_verified_at: datetime | None = None
    min_z_m: float | None = None
    max_z_m: float | None = None
    active: bool | None = None
    revision: int | None = None


class LayoutMutationOut(BaseModel):
    revision: int
    items: list[dict]
    validation_warnings: list[dict[str, str]]


class LayoutBatchIn(BaseModel):
    items: list[LayoutEntityIn] = Field(min_length=1, max_length=1000)
    revision: int | None = None


class LayoutVersionCreate(BaseModel):
    source: str = Field(default="manual", min_length=1, max_length=64)


class LayoutValidationOut(BaseModel):
    valid: bool
    revision: int
    issues: list[dict]


class WarehouseLayoutBinOut(BaseModel):
    id: int
    aisle_code: str
    rack_code: str
    shelf_level: int
    bin_code: str
    geometry: dict


class WarehouseSafetyZoneOut(BaseModel):
    id: int
    code: str
    kind: str
    geometry: dict
    min_z_m: float | None
    max_z_m: float | None
    active: bool


class WarehouseLayoutOut(BaseModel):
    id: int
    warehouse_map_id: int
    coordinate_frame_id: int
    version: int
    revision: int
    status: str
    source: str
    provenance_status: str
    artifact_set_id: int | None
    input_checksum: str | None
    algorithm_version: str | None
    created_at: datetime
    locked_at: datetime | None
    bins: list[WarehouseLayoutBinOut]
    safety_zones: list[WarehouseSafetyZoneOut]


__all__ = [
    "LayoutBatchIn",
    "LayoutEntityIn",
    "LayoutEntityPage",
    "LayoutEntityPatch",
    "LayoutMutationOut",
    "LayoutValidationOut",
    "LayoutVersionCreate",
    "WarehouseLayoutBinOut",
    "WarehouseLayoutOut",
    "WarehouseSafetyZoneOut",
]

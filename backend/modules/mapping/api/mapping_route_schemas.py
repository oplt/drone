from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class MappingArtifactsIn(BaseModel):
    orthomosaic: bool = True
    dsm: bool = True
    dtm: bool = False
    textured_mesh: bool = True
    point_cloud: bool = False
    xyz_tiles: bool = True


class MappingDroneSyncIn(BaseModel):
    source_dir: str | None = None
    recursive: bool = True


class MappingJobCreateIn(BaseModel):
    field_id: int
    processor: str = "webodm"
    input_source: Literal["upload", "drone_sync"] = "upload"
    drone_sync: MappingDroneSyncIn | None = None
    artifacts: MappingArtifactsIn = Field(default_factory=MappingArtifactsIn)
    webodm_options: dict[str, Any] = Field(default_factory=dict)
    start_immediately: bool = True

    @model_validator(mode="after")
    def _validate_input_source(self) -> MappingJobCreateIn:
        if self.processor.strip().lower() != "webodm":
            raise ValueError("Only processor='webodm' is currently supported.")
        if self.input_source == "drone_sync" and self.start_immediately is False:
            raise ValueError("input_source='drone_sync' requires start_immediately=true.")
        if self.input_source == "upload" and self.start_immediately is True:
            raise ValueError(
                "input_source='upload' requires start_immediately=false. "
                "Upload images first, then call /mapping/jobs/{job_id}/start."
            )
        return self


class MappingJobCreateOut(BaseModel):
    job_id: int
    field_id: int
    model_id: int
    status: str
    processor: str


class MappingAssetOut(BaseModel):
    id: int
    type: str
    url: str
    meta_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MappingJobStatusOut(BaseModel):
    job_id: int
    field_id: int
    model_id: int
    status: str
    progress: int
    created_at: datetime
    error: str | None = None
    processor: str
    processor_task_id: str | None = None
    assets: list[MappingAssetOut] = Field(default_factory=list)


class MappingJobUploadOut(BaseModel):
    job_id: int
    uploaded_count: int
    uploaded_paths: list[str]


class MappingJobDeleteOut(BaseModel):
    job_id: int
    deleted: bool = True


class FieldModelVersionOut(BaseModel):
    id: int
    version: int
    status: str
    created_at: datetime
    coordinate_system: str = "EPSG:4326"


class FieldRegistryOut(BaseModel):
    field_id: int
    field_name: str
    owner_id: int
    coordinate_system: str = "EPSG:4326"
    versions: list[FieldModelVersionOut]


class MappingSignedUrlOut(BaseModel):
    asset_id: int
    asset_type: str
    expires_at: datetime
    relative_url: str
    url: str
    path: str | None = None

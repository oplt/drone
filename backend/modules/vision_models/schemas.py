from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _clean_name(value: str) -> str:
    cleaned = "_".join(value.strip().lower().replace("-", " ").split())
    if not cleaned:
        raise ValueError("Class name cannot be empty")
    if not all(char.isalnum() or char == "_" for char in cleaned):
        raise ValueError(
            "Class names may contain letters, numbers, spaces, hyphens, or underscores"
        )
    return cleaned


class VisionClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _clean_name(value)


class VisionClassOut(BaseModel):
    id: str
    name: str
    class_index: int
    model_config = {"from_attributes": True}


class VisionProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    crop: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    task_type: Literal["detection"] = "detection"
    classes: list[VisionClassIn] = Field(min_length=1, max_length=100)

    @field_validator("name", "crop")
    @classmethod
    def trim_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned

    @field_validator("classes")
    @classmethod
    def unique_classes(cls, values: list[VisionClassIn]) -> list[VisionClassIn]:
        names = [item.name.casefold() for item in values]
        if len(names) != len(set(names)):
            raise ValueError("Class names must be unique")
        return values


class VisionProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    crop: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    classes: list[VisionClassIn] | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("classes")
    @classmethod
    def unique_classes(cls, values: list[VisionClassIn] | None) -> list[VisionClassIn] | None:
        if values is None:
            return None
        names = [item.name.casefold() for item in values]
        if len(names) != len(set(names)):
            raise ValueError("Class names must be unique")
        return values


class VisionProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    crop: str
    task_type: str
    status: str
    classes: list[VisionClassOut]
    dataset_count: int = 0
    latest_dataset_status: str | None = None
    latest_model_version: int | None = None
    production_model_version: int | None = None
    created_at: datetime
    updated_at: datetime


class DatasetOut(BaseModel):
    id: str
    project_id: str
    version: int
    status: str
    source_count: int
    image_count: int
    labeled_count: int
    reviewed_count: int
    selected_count: int
    train_count: int
    val_count: int
    test_count: int
    manifest_checksum: str | None
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AnnotationIn(BaseModel):
    id: str | None = None
    class_id: str
    x1: float = Field(ge=0, allow_inf_nan=False)
    y1: float = Field(ge=0, allow_inf_nan=False)
    x2: float = Field(ge=0, allow_inf_nan=False)
    y2: float = Field(ge=0, allow_inf_nan=False)
    source: Literal["manual", "auto", "imported"] = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def ordered_coordinates(self) -> AnnotationIn:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Bounding-box maximums must exceed minimums")
        return self


class AnnotationOut(BaseModel):
    id: str
    class_id: str
    annotation_type: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float | None
    source: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class AnnotationReplace(BaseModel):
    annotations: list[AnnotationIn] = Field(max_length=2000)
    reviewed: bool = True


class DatasetImageOut(BaseModel):
    id: str
    dataset_id: str
    content_url: str
    thumbnail_url: str
    source_type: str
    source_video_id: str | None
    mission_id: str | None
    field_id: int | None
    frame_index: int | None
    timestamp_seconds: float | None
    width: int
    height: int
    quality_score: float | None
    selected: bool
    split: str | None
    annotation_status: str
    annotations: list[AnnotationOut]
    lat: float | None
    lon: float | None
    altitude_m: float | None
    heading_deg: float | None
    metadata: dict[str, Any]
    created_at: datetime


class DatasetImagePage(BaseModel):
    items: list[DatasetImageOut]
    total: int
    offset: int
    limit: int


class ImageSelectionPatch(BaseModel):
    selected: bool


class ImageUploadResult(BaseModel):
    added: int
    duplicates: int
    rejected: list[str]
    images: list[DatasetImageOut]


class ExtractFramesRequest(BaseModel):
    video_id: str
    interval_seconds: float = Field(default=1.0, ge=0.2, le=30)
    max_frames: int | None = Field(default=None, ge=1, le=10_000)


class ExtractFramesOut(BaseModel):
    candidate_frames: int
    rejected_quality: int
    rejected_duplicates: int
    selected_frames: int
    effective_interval_seconds: float
    dataset: DatasetOut


class AnnotationImportOut(BaseModel):
    images_updated: int
    annotations_imported: int


class TrainingRunCreate(BaseModel):
    dataset_id: str
    base_model: Literal["yolo26n.pt", "yolo26s.pt"] = "yolo26s.pt"
    preset: Literal["fast", "balanced", "high_accuracy"] = "balanced"


class TrainingRunOut(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    status: str
    trainer: str
    base_model: str
    preset: str
    epochs: int
    total_epochs: int
    image_size: int
    batch_size: int
    device: str
    progress: float
    current_epoch: int
    metrics: dict[str, Any]
    error: str | None
    model_version_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ModelVersionOut(BaseModel):
    id: str
    model_id: str
    project_id: str
    training_run_id: str
    dataset_id: str
    name: str
    crop: str
    task_type: str
    version: int
    architecture: str
    status: str
    classes: list[str]
    metrics: dict[str, Any]
    created_at: datetime


class ModelEvaluationOut(BaseModel):
    model_version_id: str
    model_name: str
    version: int
    state: Literal["completed"]
    metrics: dict[str, Any]
    summary: dict[str, float | None]
    per_class: list[dict[str, Any]]
    confusion_matrix: list[list[float]] | None
    confusion_matrix_labels: list[str]
    dataset_id: str
    dataset_version: int
    dataset_image_count: int
    test_image_count: int
    dataset_checksum: str | None
    split: Literal["test"]
    image_size: int
    base_model: str
    preset: str
    training_date: datetime
    evaluated_at: datetime
    artifacts: list[dict[str, str]]

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath

from pydantic import BaseModel, Field, field_validator

BUILTIN_MODEL_NAMES = frozenset(
    {
        "yolo26n.pt",
        "yolo26s.pt",
        "yolo26n-seg.pt",
        "yolo26s-seg.pt",
    }
)
CUSTOM_MODEL_PREFIX = "backend/storage/ml_models/"


class VideoAssetOut(BaseModel):
    id: str
    mission_id: str | None = None
    field_id: int | None = None
    original_filename: str
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyzeVideoRequest(BaseModel):
    model_name: str = Field(
        default="yolo26s.pt",
        examples=["yolo26n.pt", "yolo26s.pt", "yolo26n-seg.pt", "yolo26s-seg.pt"],
    )
    frame_stride_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    confidence_threshold: float = Field(default=0.35, ge=0.01, le=0.99)

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, model_name: str) -> str:
        if model_name in BUILTIN_MODEL_NAMES:
            return model_name
        if model_name.startswith(CUSTOM_MODEL_PREFIX):
            path = PurePosixPath(model_name)
            if ".." not in path.parts and path.suffix == ".pt":
                return model_name
        raise ValueError("Select a built-in YOLO26 model or a local storage/ml_models/ model.")


class VideoAnalysisJobOut(BaseModel):
    id: str
    video_id: str
    mission_id: str | None = None
    status: str
    progress: float
    error: str | None = None
    model_name: str
    model_version: str
    source_checksum: str | None = None
    frame_stride_seconds: float
    confidence_threshold: float
    frames_received: int = 0
    frames_processed: int = 0
    frames_dropped: int = 0
    frames_failed: int = 0
    total_inference_latency_ms: float = 0.0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VideoDetectionOut(BaseModel):
    id: str
    job_id: str
    video_id: str
    mission_id: str | None = None
    frame_index: int
    timestamp_seconds: float
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    track_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    altitude_m: float | None = None
    heading_deg: float | None = None
    evidence_path: str | None = None

    model_config = {"from_attributes": True}

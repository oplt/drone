from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.modules.video_analysis.evidence import EvidenceRef

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
    captured_at: datetime | None = None
    capture_time_source: str = "unknown"
    capture_timezone: str | None = None
    capture_time_uncertainty_seconds: float | None = None
    sync_offset_seconds: float = 0.0
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
    model_version_id: str | None = None
    small_object_mode: bool = False
    tracking_enabled: bool = False
    tracker_type: Literal["bytetrack"] = "bytetrack"

    @model_validator(mode="after")
    def validate_tracking_stride(self) -> AnalyzeVideoRequest:
        if self.tracking_enabled and self.frame_stride_seconds > 2.0:
            raise ValueError("Tracking requires a sampling interval of 2 seconds or less.")
        return self

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
    orchestration_key: str | None = None
    progress: float
    error: str | None = None
    model_name: str
    model_version_id: str | None = None
    small_object_mode: bool = False
    tracking_enabled: bool = False
    tracker_type: Literal["bytetrack"] = "bytetrack"
    model_version: str
    loaded_model_hash: str | None = None
    source_checksum: str | None = None
    frame_stride_seconds: float
    confidence_threshold: float
    frames_received: int = 0
    frames_decoded: int = 0
    frames_attempted: int = 0
    frames_processed: int = 0
    frames_persisted: int = 0
    frames_dropped: int = 0
    frames_failed: int = 0
    total_inference_latency_ms: float = 0.0
    attempt: int = 0
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    terminal_reason_code: str | None = None
    terminal_stage: str | None = None
    stage_timings: dict[str, float] = Field(default_factory=dict)
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
    evidence: EvidenceRef | None = None
    evidence_url: str | None = None
    evidence_path: None = None
    telemetry_match_quality: str | None = None
    telemetry_match_delta_ms: float | None = None
    telemetry_match_method: str | None = None
    telemetry_match_version: str | None = None

    @model_validator(mode="before")
    @classmethod
    def hide_local_path_and_expand_metadata(cls, value: Any) -> Any:
        if isinstance(value, dict):
            data = dict(value)
            raw = dict(data.get("raw") or {})
            storage = data.get("storage_object")
        else:
            raw = dict(getattr(value, "raw", None) or {})
            storage = getattr(value, "storage_object", None)
            data = {
                name: getattr(value, name)
                for name in (
                    "id", "job_id", "video_id", "mission_id", "frame_index",
                    "timestamp_seconds", "label", "confidence", "x1", "y1",
                    "x2", "y2", "track_id", "lat", "lon", "altitude_m",
                    "heading_deg",
                )
            }
        data["evidence_path"] = None
        data["telemetry_match_quality"] = raw.get("telemetry_match_quality")
        data["telemetry_match_delta_ms"] = raw.get(
            "telemetry_match_delta_ms", raw.get("telemetry_error_ms")
        )
        data["telemetry_match_method"] = raw.get("telemetry_match_method", "nearest")
        data["telemetry_match_version"] = raw.get("telemetry_match_version")
        if storage is not None:
            available = getattr(storage, "state", None) == "final"
            spatial = (
                {"lat": data["lat"], "lon": data["lon"]}
                if data.get("lat") is not None and data.get("lon") is not None
                else None
            )
            data["evidence"] = {
                "source_entity_id": data["id"],
                "frame_index": data["frame_index"],
                "timestamp": data["timestamp_seconds"],
                "storage_object_id": storage.id,
                "checksum": storage.checksum,
                "availability": "available" if available else "missing",
                "spatial": spatial,
                "provenance": {
                    "job_id": data["job_id"],
                    "model_version": raw.get("model_version"),
                    "loaded_model_hash": raw.get("loaded_model_hash"),
                },
            }
            data["evidence_url"] = (
                f"/video-analysis/evidence/{data['id']}/content" if available else None
            )
        return data

    model_config = {"from_attributes": True}


class ConfidenceDistribution(BaseModel):
    minimum: float | None = None
    mean: float | None = None
    maximum: float | None = None


class VideoAnalysisSummaryOut(BaseModel):
    job_id: str
    frames_analyzed: int
    detections_by_class: dict[str, int]
    unique_tracked_objects_by_class: dict[str, int]
    confidence_distribution: ConfidenceDistribution
    model_name: str
    model_version: str
    model_version_id: str | None = None
    registered_model: dict[str, Any] | None = None
    tracking_enabled: bool
    tracker_type: Literal["bytetrack"]
    small_object_mode: bool
    frame_stride_seconds: float
    confidence_threshold: float


class VideoDetectionPageOut(BaseModel):
    """Cursor page; fetch next_cursor while has_more is true."""

    items: list[VideoDetectionOut]
    next_cursor: str | None = None
    has_more: bool
    job_version: int
    status: str
    total_estimate: int | None = None


class DetectionAggregateBucket(BaseModel):
    start_seconds: float
    end_seconds: float
    class_counts: dict[str, int]


class VideoDetectionAggregateOut(BaseModel):
    job_id: str
    bucket_seconds: float
    buckets: list[DetectionAggregateBucket]

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class MLRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = False
    auto_start: bool = False
    stream_source: str = ""
    detector_model_path: str = "yolov8n.pt"
    detector_conf: float = 0.35
    detector_iou: float = 0.45
    frame_stride: int = Field(default=2, ge=1)
    target_fps: int = Field(default=8, ge=1)
    enable_motion_prefilter: bool = True
    min_motion_area: int = Field(default=1500, ge=100)
    loitering_seconds: int = Field(default=12, ge=1)
    evidence_dir: str = "backend/storage/ml_evidence"
    debug_dir: str = "backend/storage/ml_debug"
    emit_websocket_events: bool = True
    save_debug_frames: bool = True
    max_duplicate_event_s: float = 10.0
    max_events_per_track: int = Field(default=8, ge=1)
    event_sink_mode: str = "http"  # "http" | "noop"
    event_sink_url: str = "http://127.0.0.1:8000/api/events"


ml_settings = MLRuntimeSettings()

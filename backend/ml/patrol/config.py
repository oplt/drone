from __future__ import annotations

import os
from dataclasses import dataclass


_BOOL_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MLRuntimeSettings:
    enabled: bool = os.getenv("ML_ENABLED", "0").strip().lower() in _BOOL_TRUE
    auto_start: bool = os.getenv("ML_AUTO_START", "0").strip().lower() in _BOOL_TRUE
    stream_source: str = os.getenv("ML_STREAM_SOURCE", "")
    detector_model_path: str = os.getenv("ML_DETECTOR_MODEL_PATH", "yolov8n.pt")
    detector_conf: float = float(os.getenv("ML_DETECTOR_CONF", "0.35"))
    detector_iou: float = float(os.getenv("ML_DETECTOR_IOU", "0.45"))
    frame_stride: int = max(1, int(os.getenv("ML_FRAME_STRIDE", "2")))
    target_fps: int = max(1, int(os.getenv("ML_TARGET_FPS", "8")))
    enable_motion_prefilter: bool = os.getenv("ML_ENABLE_MOTION_PREFILTER", "1").strip().lower() in _BOOL_TRUE
    min_motion_area: int = max(100, int(os.getenv("ML_MIN_MOTION_AREA", "1500")))
    loitering_seconds: int = max(1, int(os.getenv("ML_LOITERING_SECONDS", "12")))
    evidence_dir: str = os.getenv("ML_EVIDENCE_DIR", "backend/storage/ml_evidence")
    debug_dir: str = os.getenv("ML_DEBUG_DIR", "backend/storage/ml_debug")
    emit_websocket_events: bool = os.getenv("ML_EMIT_WEBSOCKET_EVENTS", "1").strip().lower() in _BOOL_TRUE
    save_debug_frames: bool = os.getenv("ML_SAVE_DEBUG_FRAMES", "1").strip().lower() in _BOOL_TRUE
    max_duplicate_event_s: float = float(os.getenv("ML_MAX_DUPLICATE_EVENT_S", "10"))
    max_events_per_track: int = max(1, int(os.getenv("ML_MAX_EVENTS_PER_TRACK", "8")))
    event_sink_mode: str = "http"   # "http" | "noop"
    event_sink_url: str = "http://127.0.0.1:8000/api/events"


ml_settings = MLRuntimeSettings()

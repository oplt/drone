from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class VisionRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    vision_storage_dir: str = "backend/storage/vision"
    vision_max_image_bytes: int = 20 * 1024 * 1024
    vision_max_images_per_request: int = 100
    vision_max_extraction_frames: int = 2_000
    vision_max_active_training_runs_per_org: int = 1
    celery_vision_training_queue: str = "vision-training"
    celery_vision_training_time_limit_seconds: int = 6 * 60 * 60
    celery_vision_training_soft_time_limit_seconds: int = 5 * 60 * 60 + 50 * 60
    video_sahi_slice_height: int = 640
    video_sahi_slice_width: int = 640
    video_sahi_overlap_height_ratio: float = 0.2
    video_sahi_overlap_width_ratio: float = 0.2
    video_sahi_postprocess_match_threshold: float = 0.5


vision_settings = VisionRuntimeSettings()

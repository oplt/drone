"""Bounded media pipeline stage timing metrics for video and agriculture paths."""

from __future__ import annotations

from backend.observability import prometheus_metrics
from backend.observability.metrics import record as metric_record

PIPELINE_VIDEO = "video"
PIPELINE_AGRICULTURE = "agriculture"

MEDIA_PIPELINE_STAGES = frozenset(
    {
        "queue_wait",
        "media_probe",
        "decode",
        "frame_sampling",
        "preprocessing",
        "inference",
        "tracking",
        "telemetry_matching",
        "evidence_generation",
        "database_persistence",
        "agriculture_aggregation",
        "export_generation",
        "summary",
        "total",
    }
)

_STAGE_ALIASES = {
    "crop": "evidence_generation",
    "persist": "database_persistence",
    "telemetry": "telemetry_matching",
    "model_loading": "preprocessing",
    "source_validation": "media_probe",
    "ingest": "media_probe",
    "quality": "preprocessing",
    "rgb_inference": "inference",
    "segmentation": "inference",
    "video_inference": "inference",
    "observation_aggregation": "agriculture_aggregation",
    "geospatial_aggregation": "agriculture_aggregation",
    "sensor_fusion": "agriculture_aggregation",
    "temporal_comparison": "agriculture_aggregation",
    "exports": "export_generation",
    "pipeline_execution": "agriculture_aggregation",
}


def normalize_media_pipeline_stage(stage: str) -> str | None:
    normalized = _STAGE_ALIASES.get(stage, stage.strip().lower())
    if normalized not in MEDIA_PIPELINE_STAGES:
        return None
    return normalized


def record_media_pipeline_stage_ms(
    duration_ms: float,
    *,
    stage: str,
    pipeline: str,
) -> None:
    if duration_ms < 0:
        return
    canonical = normalize_media_pipeline_stage(stage)
    if canonical is None:
        return
    attrs = {"pipeline": pipeline, "stage": canonical}
    metric_record("media_pipeline_stage_duration", duration_ms, attrs)
    prometheus_metrics.media_pipeline_stage_duration_seconds.labels(
        pipeline=pipeline,
        stage=canonical,
    ).observe(duration_ms / 1000.0)
    # Preserve legacy video histogram consumers keyed only by stage name.
    if pipeline == PIPELINE_VIDEO:
        metric_record("video_stage_duration", duration_ms, {"stage": stage})


def record_media_pipeline_stages_ms(
    timings: dict[str, float],
    *,
    pipeline: str,
) -> None:
    for stage, duration_ms in timings.items():
        record_media_pipeline_stage_ms(duration_ms, stage=stage, pipeline=pipeline)

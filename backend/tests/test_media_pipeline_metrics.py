from __future__ import annotations

import pytest

from backend.observability import prometheus_metrics
from backend.observability.media_pipeline_metrics import (
    MEDIA_PIPELINE_STAGES,
    PIPELINE_AGRICULTURE,
    PIPELINE_VIDEO,
    normalize_media_pipeline_stage,
    record_media_pipeline_stage_ms,
)


def test_normalize_media_pipeline_stage_maps_aliases() -> None:
    assert normalize_media_pipeline_stage("crop") == "evidence_generation"
    assert normalize_media_pipeline_stage("persist") == "database_persistence"
    assert normalize_media_pipeline_stage("observation_aggregation") == "agriculture_aggregation"
    assert normalize_media_pipeline_stage("exports") == "export_generation"


def test_normalize_media_pipeline_stage_rejects_unknown_labels() -> None:
    assert normalize_media_pipeline_stage("job-123-custom") is None
    assert normalize_media_pipeline_stage("") is None


def test_record_media_pipeline_stage_ms_uses_bounded_prometheus_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, str, float]] = []

    class _Observer:
        def __init__(self, pipeline: str, stage: str) -> None:
            self.pipeline = pipeline
            self.stage = stage

        def observe(self, value: float) -> None:
            observed.append((self.pipeline, self.stage, value))

    def _labels(*, pipeline: str, stage: str) -> _Observer:
        return _Observer(pipeline, stage)

    metric_calls: list[tuple[str, float, dict[str, str]]] = []

    def _record(name: str, value: float, attrs: dict[str, str] | None = None) -> None:
        metric_calls.append((name, value, dict(attrs or {})))

    monkeypatch.setattr(
        prometheus_metrics.media_pipeline_stage_duration_seconds,
        "labels",
        _labels,
    )
    monkeypatch.setattr(
        "backend.observability.media_pipeline_metrics.metric_record",
        _record,
    )

    record_media_pipeline_stage_ms(
        2500.0,
        stage="decode",
        pipeline=PIPELINE_VIDEO,
    )

    assert observed == [("video", "decode", 2.5)]
    assert (
        "media_pipeline_stage_duration",
        2500.0,
        {"pipeline": PIPELINE_VIDEO, "stage": "decode"},
    ) in metric_calls


def test_canonical_stage_set_matches_task_contract() -> None:
    required = {
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
    }
    assert required.issubset(MEDIA_PIPELINE_STAGES)


def test_agriculture_quality_maps_to_preprocessing() -> None:
    assert normalize_media_pipeline_stage("quality") == "preprocessing"

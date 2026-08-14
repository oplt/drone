from __future__ import annotations

from backend.modules.video_analysis.models import VideoAnalysisJob


def test_video_analysis_job_declares_status_lease_composite_index() -> None:
    index_names = {index.name for index in VideoAnalysisJob.__table__.indexes}
    assert "ix_video_analysis_jobs_status_lease" in index_names


def test_video_asset_status_column_is_indexed() -> None:
    from backend.modules.video_analysis.models import VideoAsset

    status_column = VideoAsset.__table__.c.status
    assert any(index.columns.contains_column(status_column) for index in VideoAsset.__table__.indexes)


def test_agriculture_telemetry_receipt_unique_per_flight_key() -> None:
    from backend.modules.agriculture.models import AgricultureTelemetryReceipt

    names = {constraint.name for constraint in AgricultureTelemetryReceipt.__table__.constraints}
    assert "uq_agri_telemetry_receipt_flight_key" in names

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.modules.agriculture.inference_reuse import build_inference_reuse_summary


class _ScalarResult:
    def __init__(self, rows: list[object]):
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class FakeDatabase:
    def __init__(self, *, links: list[object], prior_runs: dict[str, object]):
        self.links = links
        self.prior_runs = prior_runs

    async def scalars(self, _statement):
        return _ScalarResult(self.links)

    async def get(self, _model, key: str):
        return self.prior_runs.get(key)


@pytest.mark.asyncio
async def test_build_inference_reuse_summary_marks_reused_video_jobs() -> None:
    completed_at = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    db = FakeDatabase(
        links=[
            SimpleNamespace(
                capability_id="weed_detection",
                video_id="video-1",
                video_job_id="job-old",
                inference_snapshot={
                    "reused_completed_job": True,
                    "reused_from_run_id": "run-old",
                    "source_checksum": "sha256:video",
                    "model_checksum": "sha256:model",
                    "vision_model_version_id": "version-1",
                    "inference_profile": {"frame_stride_seconds": 1.0},
                },
            )
        ],
        prior_runs={
            "run-old": SimpleNamespace(finished_at=completed_at),
        },
    )
    run = SimpleNamespace(id="run-new", input_checksum="sha256:input")

    summary = await build_inference_reuse_summary(db, run=run)

    assert summary is not None
    assert summary.reused_job_count == 1
    assert summary.fully_reused is True
    assert summary.details[0].reused_from_run_id == "run-old"
    assert summary.details[0].original_completed_at == completed_at


@pytest.mark.asyncio
async def test_build_inference_reuse_summary_returns_zero_reuse_for_fresh_jobs() -> None:
    db = FakeDatabase(
        links=[
            SimpleNamespace(
                capability_id="weed_detection",
                video_id="video-1",
                video_job_id="job-new",
                inference_snapshot={"reused_completed_job": False},
            )
        ],
        prior_runs={},
    )
    run = SimpleNamespace(id="run-new", input_checksum="sha256:input")

    summary = await build_inference_reuse_summary(db, run=run)

    assert summary is not None
    assert summary.reused_job_count == 0
    assert summary.fully_reused is False

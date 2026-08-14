from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureAnalysisVideoJob
from backend.modules.agriculture.schemas import (
    AnalysisRunOut,
    InferenceReuseDetailOut,
    InferenceReuseSummaryOut,
)


async def build_inference_reuse_summary(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
) -> InferenceReuseSummaryOut | None:
    links = list(
        (
            await db.scalars(
                select(AgricultureAnalysisVideoJob).where(
                    AgricultureAnalysisVideoJob.run_id == run.id
                )
            )
        ).all()
    )
    if not links:
        return None

    prior_runs: dict[str, AgricultureAnalysisRun | None] = {}
    details: list[InferenceReuseDetailOut] = []
    reused_job_count = 0

    for link in links:
        snapshot = dict(link.inference_snapshot or {})
        reused = bool(snapshot.get("reused_completed_job"))
        if reused:
            reused_job_count += 1
        prior_run_id = snapshot.get("reused_from_run_id")
        prior_run_id_str = str(prior_run_id) if prior_run_id else None
        original_completed_at: datetime | None = None
        if prior_run_id_str:
            if prior_run_id_str not in prior_runs:
                prior_runs[prior_run_id_str] = await db.get(
                    AgricultureAnalysisRun, prior_run_id_str
                )
            original_completed_at = prior_runs[prior_run_id_str].finished_at if prior_runs[prior_run_id_str] else None
        if original_completed_at is None:
            completed_raw = snapshot.get("completed_at")
            if completed_raw:
                try:
                    original_completed_at = datetime.fromisoformat(str(completed_raw))
                except ValueError:
                    original_completed_at = None

        details.append(
            InferenceReuseDetailOut(
                capability_id=link.capability_id,
                video_id=link.video_id,
                video_job_id=link.video_job_id,
                reused=reused,
                reused_from_run_id=prior_run_id_str,
                source_checksum=_optional_str(snapshot.get("source_checksum")),
                model_checksum=_optional_str(snapshot.get("model_checksum")),
                vision_model_version_id=_optional_str(
                    snapshot.get("vision_model_version_id")
                ),
                inference_profile=_profile_dict(snapshot.get("inference_profile")),
                original_completed_at=original_completed_at,
            )
        )

    return InferenceReuseSummaryOut(
        run_input_checksum=run.input_checksum,
        reused_job_count=reused_job_count,
        total_job_count=len(links),
        fully_reused=reused_job_count == len(links) and len(links) > 0,
        details=details,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _profile_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


async def serialize_analysis_run(
    db: AsyncSession,
    run: AgricultureAnalysisRun,
) -> AnalysisRunOut:
    reuse = await build_inference_reuse_summary(db, run=run)
    return AnalysisRunOut.model_validate(run).model_copy(
        update={"inference_reuse": reuse},
    )

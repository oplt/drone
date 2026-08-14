"""Durable execution contract and continuation dispatch for agriculture stages."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select

from backend.core.config.runtime import settings
from backend.core.database.session import Session
from backend.modules.agriculture.lifecycle import append_analysis_event
from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureAnalysisStage
from backend.modules.agriculture.queue import agriculture_analysis_queue
from backend.modules.agriculture.repository import agriculture_repository
from backend.modules.agriculture.stage_operations import (
    STAGE_VERSIONS,
    aggregate_geospatial_results,
    build_export_result,
    checksum_payload,
    compare_temporal_results,
    coordinate_rgb_inference,
    fuse_sensor_results,
    persist_segmentation_result,
    stage_input_checksum,
)
from backend.observability.media_pipeline_metrics import (
    PIPELINE_AGRICULTURE,
    record_media_pipeline_stage_ms,
)

NEXT_STAGE = {
    "rgb_inference": "geospatial_aggregation",
    "geospatial_aggregation": "segmentation",
    "segmentation": "temporal_comparison",
    "temporal_comparison": "sensor_fusion",
    "sensor_fusion": "exports",
    "exports": None,
}


def queue_for_stage(stage_name: str) -> str:
    return getattr(
        settings,
        {
            "rgb_inference": "celery_agriculture_inference_queue",
            "geospatial_aggregation": "celery_agriculture_geospatial_queue",
            "segmentation": "celery_agriculture_segmentation_queue",
            "temporal_comparison": "celery_agriculture_temporal_queue",
            "sensor_fusion": "celery_agriculture_fusion_queue",
            "exports": "celery_agriculture_exports_queue",
        }[stage_name],
    )


async def _dispatch_continuation(
    *,
    run_id: str,
    stage_name: str,
    output_checksum: str,
    cluster_radius_m: float,
) -> str | None:
    next_stage = NEXT_STAGE[stage_name]
    if next_stage is None:
        return None
    async with Session() as db:
        run = await db.get(AgricultureAnalysisRun, run_id)
        if run is None or run.status == "cancelled":
            return None
        next_checksum = stage_input_checksum(
            run,
            next_stage,
            upstream_checksum=output_checksum,
            extra={"cluster_radius_m": cluster_radius_m},
        )
    return agriculture_analysis_queue.enqueue_stage(
        stage=next_stage,
        run_id=run_id,
        input_checksum=next_checksum,
        cluster_radius_m=cluster_radius_m,
    )


async def _run_operation(
    db,
    *,
    stage_name: str,
    run,
    flight,
    cluster_radius_m: float,
    export_id: str | None,
):
    if stage_name == "rgb_inference":
        return await coordinate_rgb_inference(db, run=run, flight=flight)
    if stage_name == "geospatial_aggregation":
        return await aggregate_geospatial_results(
            db,
            run=run,
            flight=flight,
            cluster_radius_m=cluster_radius_m,
        )
    if stage_name == "segmentation":
        return await persist_segmentation_result(db, run=run)
    if stage_name == "temporal_comparison":
        return await compare_temporal_results(db, run=run, flight=flight)
    if stage_name == "sensor_fusion":
        return await fuse_sensor_results(db, run=run, flight=flight)
    if stage_name == "exports":
        return await build_export_result(db, run=run, flight=flight, export_id=export_id)
    raise ValueError(f"Unsupported agriculture stage: {stage_name}")


async def execute_stage(
    run_id: str,
    stage_name: str,
    input_checksum: str,
    *,
    task_id: str,
    queue_name: str,
    cluster_radius_m: float = 8.0,
    export_id: str | None = None,
    queue_age_seconds: float = 0.0,
) -> dict[str, str]:
    """Claim, execute, fingerprint, and continue one durable stage delivery."""
    async with Session() as db:
        run = await db.scalar(
            select(AgricultureAnalysisRun)
            .where(AgricultureAnalysisRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ValueError(f"Agriculture analysis run not found: {run_id}")
        flight = await agriculture_repository.get_flight(db, flight_id=run.flight_id)
        if flight is None:
            raise ValueError(f"Agriculture flight not found for run: {run_id}")
        if run.status == "cancelled":
            return {"run_id": run_id, "stage": stage_name, "status": "cancelled"}
        stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run_id,
                AgricultureAnalysisStage.stage_name == stage_name,
            )
            .with_for_update()
        )
        if (
            stage is not None
            and stage.status in {"completed", "skipped"}
            and stage.input_checksum == input_checksum
        ):
            output_checksum = stage.output_checksum or checksum_payload(stage.metrics or {})
            existing_task = str((stage.metrics or {}).get("continuation_task_id") or "")
            if NEXT_STAGE[stage_name] is None or existing_task:
                return {
                    "run_id": run_id,
                    "stage": stage_name,
                    "status": stage.status,
                    "continuation_task_id": existing_task,
                }
            await db.commit()
            continuation_task_id = await _dispatch_continuation(
                run_id=run_id,
                stage_name=stage_name,
                output_checksum=output_checksum,
                cluster_radius_m=cluster_radius_m,
            )
            if continuation_task_id:
                stage.metrics = {
                    **(stage.metrics or {}),
                    "continuation_task_id": continuation_task_id,
                    "next_stage": NEXT_STAGE[stage_name],
                }
                await db.commit()
            return {
                "run_id": run_id,
                "stage": stage_name,
                "status": stage.status,
                "continuation_task_id": continuation_task_id or "",
            }
        if (
            stage is not None
            and stage.status in {"completed", "skipped"}
            and stage.input_checksum != input_checksum
            and stage_name != "exports"
        ):
            raise ValueError("Completed stage checksum conflicts with non-replay input")
        if (
            stage is not None
            and stage.status == "running"
            and stage.input_checksum == input_checksum
            and stage.task_id != task_id
        ):
            return {"run_id": run_id, "stage": stage_name, "status": "duplicate"}
        if stage is None:
            stage = AgricultureAnalysisStage(run_id=run_id, stage_name=stage_name)
            db.add(stage)
        stage.input_checksum = input_checksum
        stage.execution_key = f"agri:{run_id}:{stage_name}:a{run.retry_count}:{input_checksum[:20]}"
        stage.status = "running"
        stage.progress = 0.0
        stage.error = None
        stage.dead_letter = False
        stage.retryable = True
        stage.started_at = datetime.now(UTC)
        stage.finished_at = None
        stage.attempt += 1
        stage.task_id = task_id
        stage.queue_name = queue_name
        retained_signals = dict((stage.metrics or {}).get("completion_signals") or {})
        claimed_signal_ids = set(retained_signals)
        stage.metrics = {
            "completion_signals": retained_signals,
            **({"export_id": export_id} if export_id else {}),
        }
        await append_analysis_event(
            db,
            run=run,
            flight=flight,
            event_type="stage.started",
            payload={"stage": stage_name, "attempt": stage.attempt, "queue": queue_name},
            dedupe_key=(
                f"analysis:{run.id}:{stage_name}:started:a{stage.attempt}:{input_checksum[:12]}"
            ),
        )
        await db.commit()

        started_at = monotonic()
        result = await _run_operation(
            db,
            stage_name=stage_name,
            run=run,
            flight=flight,
            cluster_radius_m=cluster_radius_m,
            export_id=export_id,
        )
        stage = await db.scalar(
            select(AgricultureAnalysisStage)
            .where(
                AgricultureAnalysisStage.run_id == run_id,
                AgricultureAnalysisStage.stage_name == stage_name,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert stage is not None
        latest_signals = dict((stage.metrics or {}).get("completion_signals") or {})
        output_checksum = checksum_payload(result.output)
        stage.status = result.status
        stage.progress = 100.0 if result.status in {"completed", "skipped"} else 0.0
        stage.output_checksum = output_checksum
        stage.finished_at = datetime.now(UTC) if result.status != "waiting_external" else None
        if result.status == "waiting_external":
            stage.execution_key = None
        stage.metrics = {
            "completion_signals": latest_signals,
            **result.output,
            "stage_version": STAGE_VERSIONS[stage_name],
            "duration_seconds": monotonic() - started_at,
            "queue_age_seconds": max(0.0, queue_age_seconds),
        }
        if result.status in {"completed", "skipped"}:
            await append_analysis_event(
                db,
                run=run,
                flight=flight,
                event_type="stage.progress",
                payload={"stage": stage_name, "status": result.status, "progress": 100.0},
                dedupe_key=(
                    f"analysis:{run.id}:{stage_name}:progress:"
                    f"a{stage.attempt}:{input_checksum[:12]}"
                ),
            )
        event_type = (
            "stage.waiting_external" if result.status == "waiting_external" else "stage.completed"
        )
        await append_analysis_event(
            db,
            run=run,
            flight=flight,
            event_type=event_type,
            payload={
                "stage": stage_name,
                "status": result.status,
                "progress": stage.progress,
                "output_checksum": output_checksum,
                "metrics": result.output,
            },
            dedupe_key=(
                f"analysis:{run.id}:{stage_name}:{result.status}:"
                f"a{stage.attempt}:{input_checksum[:12]}"
            ),
        )
        if stage_name == "exports" and export_id and result.status == "completed":
            await append_analysis_event(
                db,
                run=run,
                flight=flight,
                event_type="export.completed",
                payload={
                    "export_id": export_id,
                    "status": "ready",
                    "checksum": result.output.get("checksum"),
                    "format": result.output.get("format"),
                },
                dedupe_key=f"analysis:{run.id}:export:{export_id}:completed",
            )
        if stage.started_at is not None and stage.finished_at is not None:
            record_media_pipeline_stage_ms(
                (stage.finished_at - stage.started_at).total_seconds() * 1000.0,
                stage=stage_name,
                pipeline=PIPELINE_AGRICULTURE,
            )
        await db.commit()

        if result.status == "waiting_external":
            if stage_name == "rgb_inference" and set(latest_signals) - claimed_signal_ids:
                agriculture_analysis_queue.enqueue_stage(
                    stage="rgb_inference",
                    run_id=run_id,
                    input_checksum=input_checksum,
                    cluster_radius_m=cluster_radius_m,
                )
            return {"run_id": run_id, "stage": stage_name, "status": result.status}
        continuation_task_id = await _dispatch_continuation(
            run_id=run_id,
            stage_name=stage_name,
            output_checksum=output_checksum,
            cluster_radius_m=cluster_radius_m,
        )
        if continuation_task_id:
            async with Session() as continuation_db:
                continuation_stage = await continuation_db.scalar(
                    select(AgricultureAnalysisStage).where(
                        AgricultureAnalysisStage.run_id == run_id,
                        AgricultureAnalysisStage.stage_name == stage_name,
                    )
                )
                if continuation_stage is not None:
                    continuation_stage.metrics = {
                        **(continuation_stage.metrics or {}),
                        "continuation_task_id": continuation_task_id,
                        "next_stage": NEXT_STAGE[stage_name],
                    }
                    await continuation_db.commit()
        elif stage_name == "exports":
            async with Session() as completed_db:
                completed_run = await completed_db.get(AgricultureAnalysisRun, run_id)
                completed_flight = (
                    await agriculture_repository.get_flight(
                        completed_db, flight_id=completed_run.flight_id
                    )
                    if completed_run is not None
                    else None
                )
                if completed_run is not None and completed_flight is not None:
                    await append_analysis_event(
                        completed_db,
                        run=completed_run,
                        flight=completed_flight,
                        event_type="run.completed",
                        payload={
                            "status": completed_run.status,
                            "progress": completed_run.progress,
                        },
                        dedupe_key=(
                            f"analysis:{run_id}:workflow-completed:a{completed_run.retry_count}"
                        ),
                    )
                    await completed_db.commit()
        return {
            "run_id": run_id,
            "stage": stage_name,
            "status": result.status,
            "output_checksum": output_checksum,
        }

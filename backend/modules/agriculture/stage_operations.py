"""Business operations owned by independently routed agriculture stages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.analysis_orchestration import (
    agriculture_analysis_orchestration,
)
from backend.modules.agriculture.fusion_service import agriculture_fusion_service
from backend.modules.agriculture.models import (
    AgricultureAnalysisLayer,
    AgricultureAnalysisRun,
    AgricultureAnalysisVideoJob,
    AgricultureFlight,
    AgricultureObservation,
)
from backend.modules.agriculture.p5_models import AgricultureExportJob
from backend.modules.agriculture.p5_service import agriculture_safety_service
from backend.modules.agriculture.sensor_models import (
    AgricultureSensorReading,
    AgricultureSpectralBand,
)
from backend.modules.agriculture.service import agriculture_service
from backend.modules.agriculture.temporal import agriculture_temporal_service

STAGE_VERSIONS: dict[str, str] = {
    "rgb_inference": "rgb-coordination.v2",
    "geospatial_aggregation": "agriculture-aggregation.v2",
    "segmentation": "rgb-segmentation-products.v2",
    "temporal_comparison": "observation-change.v1",
    "sensor_fusion": "agriculture-fusion.v2",
    "exports": "agriculture-export.v2",
}


@dataclass(frozen=True)
class StageOperationResult:
    status: str = "completed"
    output: dict[str, Any] = field(default_factory=dict)


def checksum_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def stage_input_checksum(
    run: AgricultureAnalysisRun,
    stage_name: str,
    *,
    upstream_checksum: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    return checksum_payload(
        {
            "stage": stage_name,
            "stage_version": STAGE_VERSIONS[stage_name],
            "run_input_checksum": run.input_checksum,
            "run_attempt": run.retry_count,
            "upstream_checksum": upstream_checksum,
            "model_versions": run.model_versions if stage_name == "rgb_inference" else None,
            "analysis_profile": run.analysis_profile,
            "baseline_flight_id": run.baseline_flight_id,
            "extra": extra or {},
        }
    )


async def coordinate_rgb_inference(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
) -> StageOperationResult:
    state, job_ids = await agriculture_analysis_orchestration.prerequisite_state(
        db, run=run, flight=flight
    )
    links = list(
        (
            await db.scalars(
                select(AgricultureAnalysisVideoJob).where(
                    AgricultureAnalysisVideoJob.run_id == run.id
                )
            )
        ).all()
    )
    fingerprints = {
        link.video_job_id: {
            "capability_id": link.capability_id,
            "release_id": link.capability_release_id,
            "source_checksum": (link.inference_snapshot or {}).get("source_checksum"),
            "model_checksum": (link.inference_snapshot or {}).get("model_checksum"),
            "profile_digest": ((link.inference_snapshot or {}).get("inference_profile") or {}).get(
                "profile_digest"
            ),
            "reused": bool((link.inference_snapshot or {}).get("reused_completed_job")),
        }
        for link in links
    }
    output = {
        "version": STAGE_VERSIONS["rgb_inference"],
        "job_ids": job_ids,
        "job_count": len(job_ids),
        "fingerprints": fingerprints,
    }
    if state == "waiting":
        return StageOperationResult(status="waiting_external", output=output)
    if state == "failed":
        raise RuntimeError(run.error or "Required RGB inference failed")
    run.status = "orchestrating"
    run.progress = max(run.progress, 15.0)
    await db.commit()
    return StageOperationResult(output=output)


async def aggregate_geospatial_results(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
    cluster_radius_m: float,
) -> StageOperationResult:
    processed = await agriculture_service.process_analysis_run(
        db,
        run=run,
        flight=flight,
        force=False,
        cluster_radius_m=cluster_radius_m,
    )
    if processed.status == "waiting_inference":
        return StageOperationResult(
            status="waiting_external",
            output={"version": STAGE_VERSIONS["geospatial_aggregation"]},
        )
    if processed.status == "failed":
        raise RuntimeError(processed.error or "Geospatial aggregation failed")
    layer_count = int(
        await db.scalar(
            select(func.count())
            .select_from(AgricultureAnalysisLayer)
            .where(AgricultureAnalysisLayer.run_id == run.id)
        )
        or 0
    )
    observation_count = int(
        await db.scalar(
            select(func.count())
            .select_from(AgricultureObservation)
            .where(AgricultureObservation.run_id == run.id)
        )
        or 0
    )
    return StageOperationResult(
        status="skipped" if processed.status == "blocked_quality" else "completed",
        output={
            "version": STAGE_VERSIONS["geospatial_aggregation"],
            "run_status": processed.status,
            "observation_count": observation_count,
            "layer_count": layer_count,
            "quality_checksum": checksum_payload(processed.quality_gate or {}),
            "compatibility": "agriculture-analysis-results.v1",
        },
    )


async def persist_segmentation_result(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
) -> StageOperationResult:
    fallback = dict((run.quality_gate or {}).get("vision_fallback") or {})
    layer_names = ("canopy_cover", "soil", "standing_water", "row_detection")
    layers = list(
        (
            await db.scalars(
                select(AgricultureAnalysisLayer).where(
                    AgricultureAnalysisLayer.run_id == run.id,
                    AgricultureAnalysisLayer.layer_name.in_(layer_names),
                )
            )
        ).all()
    )
    if not fallback and not layers:
        return StageOperationResult(
            status="skipped",
            output={
                "version": STAGE_VERSIONS["segmentation"],
                "availability": "not_available",
                "reason": "no_segmentation_inputs_or_products",
            },
        )
    return StageOperationResult(
        output={
            "version": STAGE_VERSIONS["segmentation"],
            "method": "rgb_heuristic_fallback",
            "metrics": fallback,
            "layers": {
                layer.layer_name: {
                    "checksum": layer.checksum,
                    "feature_count": len((layer.geojson or {}).get("features", [])),
                }
                for layer in layers
            },
            "provenance": {
                "run_id": run.id,
                "quality_gate_checksum": checksum_payload(run.quality_gate or {}),
            },
        }
    )


async def compare_temporal_results(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
) -> StageOperationResult:
    reference = await agriculture_temporal_service.select_reference_flight(
        db,
        current=flight,
        override_flight_id=run.baseline_flight_id,
    )
    if reference is None:
        return StageOperationResult(
            status="skipped",
            output={
                "version": STAGE_VERSIONS["temporal_comparison"],
                "availability": "not_available",
                "reason": "no_comparable_reference_flight",
                "selection": "explicit" if run.baseline_flight_id else "automatic",
            },
        )
    result = await agriculture_temporal_service.compare(
        db,
        current=flight,
        reference_flight_id=reference.id,
    )
    output = {
        "version": STAGE_VERSIONS["temporal_comparison"],
        "status": result.get("status"),
        "reference_flight_id": reference.id,
        "selection": "explicit" if run.baseline_flight_id else "automatic",
        "source_runs": result.get("source_runs", {}),
        "methodology": result.get("methodology", {}),
        "comparability": result.get("comparability", {}),
        "summary": result.get("summary", {}),
    }
    run.audit_json = {**(run.audit_json or {}), "temporal_stage": output}
    await db.commit()
    return StageOperationResult(
        status="completed" if result.get("status") == "completed" else "skipped",
        output=output,
    )


async def fuse_sensor_results(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
) -> StageOperationResult:
    bands = list(
        (
            await db.scalars(
                select(AgricultureSpectralBand).where(
                    AgricultureSpectralBand.flight_id == flight.id
                )
            )
        ).all()
    )
    readings = list(
        (
            await db.scalars(
                select(AgricultureSensorReading).where(
                    AgricultureSensorReading.flight_id == flight.id
                )
            )
        ).all()
    )
    inventory = set((flight.profile_snapshot or {}).get("sensor_inventory") or ["rgb"])
    fusion_profile = dict((run.analysis_profile or {}).get("sensor_fusion") or {})
    supplied_inputs = any(
        fusion_profile.get(key)
        for key in (
            "band_values",
            "thermal_values_c",
            "visual_inputs",
            "environmental_context",
        )
    )
    if not bands and not readings and not supplied_inputs:
        return StageOperationResult(
            status="skipped",
            output={
                "version": STAGE_VERSIONS["sensor_fusion"],
                "availability": "not_available",
                "reason": "no_sensor_telemetry_or_fusion_inputs",
                "sensor_inventory": sorted(inventory),
            },
        )
    flight_profile = dict(flight.profile_snapshot or {})
    results = await agriculture_fusion_service.process(
        db,
        run=run,
        flight=flight,
        request={
            "requested_indices": ["ndvi", "gndvi", "ndre"] if "multispectral" in inventory else [],
            "geometries": list(fusion_profile.get("geometries") or []),
            "band_values": dict(fusion_profile.get("band_values") or {}),
            "thermal_values_c": list(fusion_profile.get("thermal_values_c") or []),
            "thermal_calibrated": bool(fusion_profile.get("thermal_calibrated")),
            "visual_inputs": dict(fusion_profile.get("visual_inputs") or {}),
            "environmental_context": dict(fusion_profile.get("environmental_context") or {}),
            "crop_context": {
                key: flight_profile.get(key)
                for key in ("crop_type", "variety", "growth_stage")
                if flight_profile.get(key) is not None
            },
            "history": dict(fusion_profile.get("history") or {}),
        },
    )
    return StageOperationResult(
        output={
            "version": STAGE_VERSIONS["sensor_fusion"],
            "result_count": len(results),
            "results": {
                item.layer_name: {
                    "status": item.status,
                    "measured": item.measured,
                    "failure_reasons": item.failure_reasons,
                }
                for item in results
            },
            "source_band_ids": [item.id for item in bands],
            "source_reading_ids": [item.id for item in readings],
        }
    )


async def build_export_result(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
    export_id: str | None,
) -> StageOperationResult:
    if export_id is None:
        return StageOperationResult(
            status="skipped",
            output={
                "version": STAGE_VERSIONS["exports"],
                "availability": "not_requested",
            },
        )
    job = await db.get(AgricultureExportJob, export_id)
    if job is None or job.run_id != run.id or job.org_id != flight.org_id:
        raise ValueError("Agriculture export job not found for this run")
    if job.status == "ready" and job.checksum:
        return StageOperationResult(
            output={
                "version": STAGE_VERSIONS["exports"],
                "export_id": job.id,
                "checksum": job.checksum,
                "format": job.format,
                "reused": True,
            }
        )
    request = dict((job.source_manifest or {}).get("request") or {})
    try:
        built = await agriculture_safety_service.create_export(
            db,
            run=run,
            flight=flight,
            request=request,
            user_id=job.requested_by_user_id,
            org_id=job.org_id,
            job=job,
        )
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:4000]
        await db.commit()
        raise
    return StageOperationResult(
        output={
            "version": STAGE_VERSIONS["exports"],
            "export_id": built.id,
            "checksum": built.checksum,
            "format": built.format,
            "byte_artifact": built.storage_key,
            "reused": False,
        }
    )

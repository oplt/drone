"""Release 4 orchestration with explicit applicability and no false precision."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.crop_insights import build_crop_risks, estimate_growth_stage, forecast_yield, summarize_growth
from backend.modules.agriculture.models import AgricultureAnalysisRun, AgricultureFlight
from backend.modules.agriculture.p4_models import AgricultureCropRisk, AgricultureGrowthMetric, AgricultureGrowthStageEstimate, AgricultureHarvestLabel, AgricultureYieldForecast
from backend.modules.agriculture.sensor_models import AgricultureFusionResult


class AgricultureCropInsightService:
    @staticmethod
    def _model_gate(*, run: AgricultureAnalysisRun, model_version_id: str | None, crop_type: str | None, growth_stage: str | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        snapshot = dict((run.model_versions or {}).get("crop_health") or {})
        reasons: list[str] = []
        if not snapshot:
            reasons.append("no_crop_health_release_on_analysis_run")
        elif model_version_id and model_version_id != snapshot.get("vision_model_version_id"):
            reasons.append("requested_model_does_not_match_analysis_provenance")
        supported_crops = {str(item).lower() for item in snapshot.get("crop_types", [])}
        if snapshot and crop_type and supported_crops and crop_type.lower() not in supported_crops:
            reasons.append("crop_outside_release_scope")
        return (
            snapshot or None,
            {
                "eligible": not reasons,
                "status": "pass" if not reasons else "not_applicable",
                "reasons": reasons,
                "task": "crop_health",
                "crop_type": crop_type,
                "growth_stage": growth_stage,
                "model_version": snapshot.get("model_version"),
                "model_version_id": snapshot.get("vision_model_version_id"),
                "release_id": snapshot.get("release_id"),
                "metrics": snapshot.get("evaluation_metrics", {}),
                "thresholds": snapshot.get("thresholds", {}),
            },
        )

    async def process_crop_risk(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any]) -> list[AgricultureCropRisk]:
        profile = flight.profile_snapshot or {}
        model, applicability = self._model_gate(run=run, model_version_id=request.get("model_version_id"), crop_type=profile.get("crop_type"), growth_stage=profile.get("growth_stage"))
        fusion_rows = list((await db.scalars(select(AgricultureFusionResult).where(AgricultureFusionResult.run_id == run.id))).all())
        fusion_risk = next((row.summary for row in fusion_rows if row.layer_name == "fusion_risk"), {})
        thermal = next((row.summary for row in fusion_rows if row.layer_name == "thermal"), {})
        index = next((row.summary for row in fusion_rows if row.layer_name in {"ndvi", "gndvi"} and row.measured), {})
        fusion_inputs = {**request.get("fusion_inputs", {}), **fusion_risk}
        if index.get("mean") is not None: fusion_inputs["ndvi_mean"] = index["mean"]
        evidence = list(dict.fromkeys([*request.get("evidence_ids", []), *(fusion_risk.get("source_ids", []) if isinstance(fusion_risk, dict) else [])]))
        payloads = build_crop_risks(visual=request.get("visual_inputs", {}), fusion=fusion_inputs, thermal={**thermal, **request.get("thermal_inputs", {})}, sensors=request.get("sensor_inputs", {}), crop_type=profile.get("crop_type"), growth_stage=profile.get("growth_stage"), history=request.get("history", {}), geometry=request.get("geometry_geojson", {}), evidence_ids=evidence, applicability=applicability, model_config={**(model.get("thresholds", {}) if model else {}), "crop_types": model.get("crop_types", []) if model else []}, model_version=str(model.get("model_version")) if model else None)
        output = []
        for payload in payloads:
            record = await db.scalar(select(AgricultureCropRisk).where(AgricultureCropRisk.run_id == run.id, AgricultureCropRisk.issue_type == payload["issue_type"]))
            if record is None:
                record = AgricultureCropRisk(run_id=run.id, flight_id=flight.id, field_id=flight.field_id, issue_type=payload["issue_type"])
                db.add(record)
            for key in ("status", "crop_type", "growth_stage", "geometry_geojson", "severity", "confidence", "trend", "uncertainty", "evidence_ids", "sensor_values", "inspection_points", "factors", "applicability", "model_version"):
                setattr(record, key, payload.get(key))
            output.append(record)
        await db.commit()
        return output

    async def process_growth_metric(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any]) -> AgricultureGrowthMetric:
        source_kind = str(request.get("source_kind", "unknown")); values = [float(value) for value in request.get("values", [])]
        if source_kind not in {"stereo", "lidar", "photogrammetry"}:
            computed = {"status": "not_measured", "units": request.get("units"), "summary": {}, "confidence": 0.0, "uncertainty": {"reasons": ["unsupported_height_or_biomass_source", "requires_stereo_lidar_or_photogrammetry"]}}
        elif not request.get("calibration_valid"):
            computed = {"status": "blocked", "units": request.get("units"), "summary": {}, "confidence": 0.0, "uncertainty": {"reasons": ["height_or_biomass_calibration_missing"]}}
        else:
            computed = summarize_growth(values, units=str(request.get("units", "m")), source_kind=source_kind, previous_mean=request.get("previous_mean"))
        record = await db.scalar(select(AgricultureGrowthMetric).where(AgricultureGrowthMetric.run_id == run.id, AgricultureGrowthMetric.metric_kind == request["metric_kind"]))
        if record is None:
            record = AgricultureGrowthMetric(run_id=run.id, flight_id=flight.id, field_id=flight.field_id, metric_kind=request["metric_kind"]); db.add(record)
        record.status = computed["status"]; record.units = computed.get("units"); record.summary = computed.get("summary", {}); record.source_ids = request.get("source_ids", []); record.source_timestamps = request.get("source_timestamps", []); record.confidence = computed.get("confidence", 0.0); record.uncertainty = computed.get("uncertainty", {}); record.evidence_ids = request.get("evidence_ids", []); record.model_version = "growth-distribution-v1"
        await db.commit()
        return record

    async def process_growth_stage(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any]) -> AgricultureGrowthStageEstimate:
        profile = flight.profile_snapshot or {}
        computed = estimate_growth_stage(crop_type=profile.get("crop_type"), context_stage=profile.get("growth_stage"), features=request.get("features", {}), history=request.get("history", []), evidence_ids=request.get("evidence_ids", []))
        record = await db.scalar(select(AgricultureGrowthStageEstimate).where(AgricultureGrowthStageEstimate.run_id == run.id))
        if record is None:
            record = AgricultureGrowthStageEstimate(run_id=run.id, flight_id=flight.id, field_id=flight.field_id); db.add(record)
        for key in ("status", "predicted_stage", "candidates", "confidence", "inputs", "evidence_ids", "uncertainty", "model_version"):
            setattr(record, key, computed.get(key))
        await db.commit()
        return record

    async def correct_growth_stage(self, db: AsyncSession, *, record: AgricultureGrowthStageEstimate, stage: str, note: str | None, user_id: int | None) -> AgricultureGrowthStageEstimate:
        record.status = "human_corrected"; record.human_stage = stage; record.correction_note = note; record.corrected_by_user_id = user_id; record.corrected_at = datetime.now(UTC); await db.commit(); await db.refresh(record); return record

    async def process_yield_forecast(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any]) -> AgricultureYieldForecast:
        labels = list((await db.scalars(select(AgricultureHarvestLabel).where(AgricultureHarvestLabel.field_id == flight.field_id).order_by(AgricultureHarvestLabel.harvest_date))).all())
        label_dicts = [{"id": row.id, "yield_value": row.yield_value, "yield_unit": row.yield_unit, "quality": row.quality} for row in labels]
        units = request.get("units") or (labels[0].yield_unit if labels else None)
        computed = forecast_yield(label_dicts, units=units, feature_adjustment=request.get("feature_adjustment", 0.0))
        flight_count = int((await db.scalar(select(func.count(AgricultureFlight.id)).where(AgricultureFlight.field_id == flight.field_id))) or 0)
        if flight_count < 2:
            computed = {**computed, "status": "not_applicable", "forecast_range": {}, "confidence_interval": {}, "confidence": 0.0, "applicability": {**computed.get("applicability", {}), "eligible": False, "reasons": [*computed.get("applicability", {}).get("reasons", []), "minimum_two_flights_required" ]}}
        record = await db.scalar(select(AgricultureYieldForecast).where(AgricultureYieldForecast.run_id == run.id))
        if record is None:
            record = AgricultureYieldForecast(run_id=run.id, flight_id=flight.id, field_id=flight.field_id); db.add(record)
        for key in ("status", "units", "forecast_range", "confidence_interval", "confidence", "factors", "applicability", "uncertainty", "harvest_label_ids"):
            setattr(record, key, computed.get(key))
        record.evidence_ids = request.get("evidence_ids", []); record.model_version = "yield-history-range-v1"
        await db.commit()
        return record


agriculture_crop_insight_service = AgricultureCropInsightService()

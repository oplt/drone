"""Application orchestration for calibration-gated multimodal outputs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.fusion import compute_vegetation_index, multimodal_risk, sensor_freshness, thermal_summary, validate_spectral_inputs
from backend.modules.agriculture.models import AgricultureAnalysisLayer, AgricultureAnalysisRun, AgricultureFlight
from backend.modules.agriculture.sensor_models import AgricultureFusionResult, AgricultureSensorCalibration, AgricultureSensorReading, AgricultureSpectralBand


def _features(values: list[float] | None, geometries: list[dict[str, Any]]) -> dict[str, Any]:
    if not values: return {"type": "FeatureCollection", "features": []}
    features = []
    for index, value in enumerate(values):
        features.append({"type": "Feature", "geometry": geometries[index] if index < len(geometries) else None, "properties": {"value": value, "sample_index": index}})
    return {"type": "FeatureCollection", "features": features}


class AgricultureFusionService:
    async def sensor_status(self, db: AsyncSession, *, flight: AgricultureFlight) -> dict[str, Any]:
        bands = list((await db.scalars(select(AgricultureSpectralBand).where(AgricultureSpectralBand.flight_id == flight.id))).all())
        readings = list((await db.scalars(select(AgricultureSensorReading).where(AgricultureSensorReading.flight_id == flight.id))).all())
        inventory = sorted(set(str(item) for item in (flight.profile_snapshot or {}).get("sensor_inventory", ["rgb"])))
        profile_calibration_ids = sorted({str(item) for item in (flight.profile_snapshot or {}).get("calibration_ids", [])})
        calibration_rows = list((await db.scalars(select(AgricultureSensorCalibration).where(AgricultureSensorCalibration.id.in_(profile_calibration_ids), AgricultureSensorCalibration.org_id == flight.org_id))).all()) if profile_calibration_ids else []
        now = datetime.now(UTC)
        calibrations = [{"id": row.id, "sensor_serial": row.sensor_serial, "sensor_type": row.sensor_type, "version": row.version, "checksum": row.checksum, "valid_from": row.valid_from, "valid_until": row.valid_until, "valid": (row.valid_from is None or row.valid_from <= now) and (row.valid_until is None or row.valid_until > now)} for row in calibration_rows]
        spectral = validate_spectral_inputs(bands) if "multispectral" in inventory else {"status": "not_required", "available_bands": sorted({row.band_name for row in bands})}
        freshness = sensor_freshness(readings)
        calibration_ids = sorted({row.calibration_id for row in bands if row.calibration_id})
        valid_profile_calibrations = {row["id"] for row in calibrations if row["valid"]}
        calibration_status = "not_required" if set(inventory) <= {"rgb"} else "pass" if profile_calibration_ids and set(profile_calibration_ids) == valid_profile_calibrations else "blocked"
        return {"flight_id": flight.id, "inventory": inventory, "spectral": spectral, "calibration_ids": calibration_ids, "profile_calibration_ids": profile_calibration_ids, "calibrations": calibrations, "calibration_status": calibration_status, "readings": freshness, "status": "pass" if spectral.get("status") in {"pass", "not_required"} and calibration_status in {"pass", "not_required"} and all(value.get("status") == "pass" for value in freshness.values()) else "warning"}

    async def process(self, db: AsyncSession, *, run: AgricultureAnalysisRun, flight: AgricultureFlight, request: dict[str, Any]) -> list[AgricultureFusionResult]:
        bands = list((await db.scalars(select(AgricultureSpectralBand).where(AgricultureSpectralBand.flight_id == flight.id))).all())
        readings = list((await db.scalars(select(AgricultureSensorReading).where(AgricultureSensorReading.flight_id == flight.id))).all())
        status = sensor_freshness(readings)
        geometries = request.get("geometries", [])
        results: list[dict[str, Any]] = []
        band_values = request.get("band_values", {})
        profile = flight.profile_snapshot or {}
        if "multispectral" not in set(profile.get("sensor_inventory", ["rgb"])):
            rgb = (run.quality_gate or {}).get("vision_fallback", {})
            results.append({"layer": "rgb_metrics", "status": "pass", "measured": True, "units": "percent", "summary": {"canopy_pct": rgb.get("canopy_pct"), "soil_pct": rgb.get("soil_pct"), "visible_water_pct": rgb.get("visible_water_pct"), "metric_semantics": "RGB-derived; not NDVI"}, "required_inputs": ["rgb"], "source_ids": [], "source_timestamps": [], "confidence": 0.6 if rgb else 0.2, "uncertainty": {"model": "rgb_heuristic_fallback"}, "evidence": [], "failure_reasons": []})
        for index_name in request.get("requested_indices", ["ndvi"]):
            validation = validate_spectral_inputs(bands, required={"red", "nir"} if index_name == "ndvi" else {"green", "nir"})
            computed = compute_vegetation_index(band_values, index_name=index_name) if validation.get("status") == "pass" else {"status": "blocked", "reason": "calibration_or_band_gate", "index": index_name}
            result_status = computed.get("status", "blocked")
            results.append({"layer": index_name, "status": result_status, "measured": result_status == "pass", "units": "unitless" if result_status == "pass" else None, "summary": {**computed, "calibration": validation}, "required_inputs": sorted(validation.get("required_bands", [])), "source_ids": [row.id for row in bands if row.band_name in validation.get("required_bands", [])], "source_timestamps": [row.capture_timestamp.isoformat() for row in bands if row.capture_timestamp and row.band_name in validation.get("required_bands", [])], "confidence": 0.9 if result_status == "pass" else 0.0, "uncertainty": computed.get("uncertainty", {"calibration": validation}), "evidence": [], "failure_reasons": validation.get("failure_reasons", []) if result_status != "pass" else [], "model_version": "ratio-index-v1"})
            if result_status == "pass": results[-1]["geojson"] = _features(computed.get("values"), geometries)
        thermal = thermal_summary(request.get("thermal_values_c", []), calibrated=bool(request.get("thermal_calibrated")) and "thermal" in set(profile.get("sensor_inventory", [])))
        results.append({"layer": "thermal", "status": thermal.get("status", "not_measured"), "measured": thermal.get("status") == "pass", "units": thermal.get("units"), "summary": thermal, "required_inputs": ["thermal_radiometric_calibration"], "source_ids": [row.id for row in bands if row.band_name == "thermal"], "source_timestamps": [row.capture_timestamp.isoformat() for row in bands if row.capture_timestamp and row.band_name == "thermal"], "confidence": 0.85 if thermal.get("status") == "pass" else 0.0, "uncertainty": thermal.get("uncertainty", {}), "evidence": [], "failure_reasons": thermal.get("failure_reasons", [thermal.get("reason")] if thermal.get("reason") else [])})
        risk = multimodal_risk(visual=request.get("visual_inputs", {}), thermal=thermal, sensor_state=status, crop_context=request.get("crop_context", {}), history=request.get("history", {}))
        results.append({"layer": "fusion_risk", "status": risk["status"], "measured": bool(risk["factors"]), "units": "risk_0_1", "summary": risk, "required_inputs": ["visual"], "source_ids": [row.id for row in readings], "source_timestamps": [row.timestamp_utc.isoformat() for row in readings], "confidence": risk["confidence"], "uncertainty": {"missing_inputs": risk["missing_inputs"]}, "evidence": [], "failure_reasons": [], "model_version": "multimodal-risk-v1"})
        output: list[AgricultureFusionResult] = []
        for payload in results:
            result = await db.scalar(select(AgricultureFusionResult).where(AgricultureFusionResult.run_id == run.id, AgricultureFusionResult.layer_name == payload["layer"]))
            if result is None: result = AgricultureFusionResult(run_id=run.id, layer_name=payload["layer"]); db.add(result)
            for key in ("status", "measured", "units", "summary", "required_inputs", "source_ids", "source_timestamps", "confidence", "uncertainty", "evidence", "failure_reasons", "model_version"): setattr(result, key, payload.get(key))
            layer_json = payload.get("geojson", {"type": "FeatureCollection", "features": []})
            layer = await db.scalar(select(AgricultureAnalysisLayer).where(AgricultureAnalysisLayer.run_id == run.id, AgricultureAnalysisLayer.layer_name == payload["layer"]))
            checksum = hashlib.sha256(json.dumps(layer_json, sort_keys=True, default=str).encode()).hexdigest()
            if layer is None: layer = AgricultureAnalysisLayer(run_id=run.id, layer_name=payload["layer"]); db.add(layer)
            layer.status = "ready" if payload.get("measured") else "not_measured"; layer.geojson = layer_json; layer.summary = payload["summary"]; layer.checksum = checksum
            output.append(result)
        await db.commit()
        return output


agriculture_fusion_service = AgricultureFusionService()

"""Deterministic P4 crop insight policies and safe model adapters."""

from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Any, Iterable


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def model_applicability(model: Any | None, reports: Iterable[Any], *, task: str, crop_type: str | None, growth_stage: str | None) -> dict[str, Any]:
    reasons: list[str] = []
    if model is None:
        reasons.append("no_model_registered")
        return {"eligible": False, "status": "not_applicable", "reasons": reasons, "task": task, "crop_type": crop_type, "growth_stage": growth_stage}
    config = dict(getattr(model, "config", {}) or {})
    if getattr(model, "status", None) != "deployed": reasons.append("model_not_deployed")
    if config.get("crop_types") and crop_type not in config["crop_types"]: reasons.append("crop_outside_training_scope")
    if config.get("growth_stages") and growth_stage not in config["growth_stages"]: reasons.append("growth_stage_outside_training_scope")
    report_rows = list(reports)
    latest = report_rows[-1] if report_rows else None
    metrics = dict(getattr(latest, "metrics", {}) or {}) if latest else {}
    min_f1 = float(config.get("minimum_f1", 0.75)); min_holdout = int(config.get("minimum_holdout_fields", 3)); max_calibration_mae = float(config.get("maximum_calibration_mae", 0.15))
    if latest is None: reasons.append("missing_validation_report")
    if float(metrics.get("f1", 0.0)) < min_f1: reasons.append("f1_below_threshold")
    if int(metrics.get("holdout_field_count", 0)) < min_holdout: reasons.append("insufficient_holdout_fields")
    if float(metrics.get("calibration_mae", 1.0)) > max_calibration_mae: reasons.append("calibration_error_above_threshold")
    drift = dict(getattr(latest, "drift", {}) or {}) if latest else {}
    if drift.get("status") == "blocked": reasons.append("drift_blocked")
    return {"eligible": not reasons, "status": "pass" if not reasons else "not_applicable", "reasons": sorted(set(reasons)), "task": task, "crop_type": crop_type, "growth_stage": growth_stage, "model_version": getattr(model, "version", None), "validation_report_id": getattr(latest, "id", None), "metrics": metrics, "thresholds": {"minimum_f1": min_f1, "minimum_holdout_fields": min_holdout, "maximum_calibration_mae": max_calibration_mae}}


def _centroid(geometry: dict[str, Any]) -> dict[str, Any] | None:
    if not geometry: return None
    if geometry.get("type") == "Point": return geometry
    coordinates = geometry.get("coordinates", [])
    if geometry.get("type") == "Polygon" and coordinates and coordinates[0]:
        ring = coordinates[0]; lon = mean(float(point[0]) for point in ring); lat = mean(float(point[1]) for point in ring)
        return {"type": "Point", "coordinates": [lon, lat]}
    if geometry.get("type") == "MultiPoint" and coordinates:
        return {"type": "Point", "coordinates": [mean(float(point[0]) for point in coordinates), mean(float(point[1]) for point in coordinates)]}
    return None


def build_crop_risks(*, visual: dict[str, Any], fusion: dict[str, Any], thermal: dict[str, Any], sensors: dict[str, Any], crop_type: str | None, growth_stage: str | None, history: dict[str, Any], geometry: dict[str, Any], evidence_ids: list[Any], applicability: dict[str, Any], model_config: dict[str, Any] | None = None, model_version: str | None = None) -> list[dict[str, Any]]:
    factors: dict[str, float] = {}
    if visual.get("canopy_stress") is not None: factors["visual_canopy_stress"] = _clamp(float(visual["canopy_stress"]))
    if fusion.get("risk_score") is not None: factors["multimodal_risk"] = _clamp(float(fusion["risk_score"]))
    if thermal.get("hot_fraction") is not None and thermal.get("status") == "pass": factors["thermal_hot_canopy"] = _clamp(float(thermal["hot_fraction"]))
    if fusion.get("ndvi_mean") is not None: factors["low_vegetation_index"] = _clamp(1.0 - (float(fusion["ndvi_mean"]) + 1.0) / 2.0)
    soil = sensors.get("soil_moisture", {})
    if soil.get("status") == "pass" and soil.get("values", {}).get("percent") is not None: factors["soil_moisture_stress"] = _clamp(1.0 - float(soil["values"]["percent"]) / 100.0)
    if not factors: return [{"issue_type": "crop_stress_signature", "status": "not_measured", "severity": 0.0, "confidence": 0.0, "trend": "unknown", "geometry_geojson": geometry, "inspection_points": [], "factors": {}, "evidence_ids": evidence_ids, "sensor_values": sensors, "uncertainty": {"reasons": ["no_validated_inputs"]}, "applicability": applicability, "model_version": model_version}]
    score = sum(factors.values()) / len(factors)
    previous = history.get("previous_risk_score")
    trend = "increasing" if previous is not None and score - float(previous) > 0.05 else "decreasing" if previous is not None and score - float(previous) < -0.05 else "stable" if previous is not None else "unknown"
    issue_type = "crop_stress_signature"
    status = "candidate" if score >= 0.45 else "normal"
    config = model_config or {}
    if applicability.get("eligible") and config.get("issue_labels"):
        label_scores = {str(key): _clamp(float(value)) for key, value in (visual.get("label_scores", {}) or {}).items()}
        configured = [(label, value) for label, value in label_scores.items() if label in config["issue_labels"] and value >= float(config.get("issue_threshold", 0.5))]
        if configured:
            issue_type, score = max(configured, key=lambda pair: pair[1]); status = "candidate"
    confidence = _clamp((0.35 + 0.5 * score) * (1.0 if applicability.get("eligible") else 0.65))
    return [{"issue_type": issue_type, "status": status, "severity": _clamp(score), "confidence": confidence, "trend": trend, "geometry_geojson": geometry, "inspection_points": [_centroid(geometry)] if _centroid(geometry) else [], "factors": factors, "evidence_ids": evidence_ids, "sensor_values": sensors, "uncertainty": {"missing_inputs": [key for key in ("thermal", "soil_moisture", "vegetation_index") if key not in sensors and key not in fusion], "policy": "candidate signature; not a confirmed disease"}, "applicability": applicability, "model_version": model_version}]


def summarize_growth(values: list[float], *, units: str, source_kind: str, previous_mean: float | None = None) -> dict[str, Any]:
    if not values: return {"status": "not_measured", "units": units, "summary": {}, "confidence": 0.0, "uncertainty": {"reasons": ["values_missing"]}}
    ordered = sorted(float(value) for value in values); average = mean(ordered); spread = pstdev(ordered) if len(ordered) > 1 else 0.0; p10 = ordered[max(0, int(round((len(ordered) - 1) * 0.1)))]; p90 = ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.9)))]; cv = spread / max(abs(average), 1e-9)
    trend = "increasing" if previous_mean is not None and average - previous_mean > max(0.01, abs(previous_mean) * 0.05) else "decreasing" if previous_mean is not None and average - previous_mean < -max(0.01, abs(previous_mean) * 0.05) else "stable" if previous_mean is not None else "unknown"
    return {"status": "pass", "units": units, "summary": {"min": ordered[0], "p10": p10, "mean": average, "median": median(ordered), "p90": p90, "max": ordered[-1], "sample_count": len(ordered), "coefficient_of_variation": cv, "uniformity_score": _clamp(1.0 - cv), "trend": trend, "source_kind": source_kind}, "confidence": _clamp(0.55 + min(0.3, len(ordered) / 1000)), "uncertainty": {"method": "distribution_summary", "stddev": spread, "small_sample": len(ordered) < 10}}


def estimate_growth_stage(*, crop_type: str | None, context_stage: str | None, features: dict[str, Any], history: list[str], evidence_ids: list[Any]) -> dict[str, Any]:
    canopy = features.get("canopy_pct")
    if canopy is None and not history and not context_stage: return {"status": "not_measured", "predicted_stage": None, "candidates": [], "confidence": 0.0, "inputs": features, "evidence_ids": evidence_ids, "uncertainty": {"reasons": ["insufficient_rgb_history_or_field_context"]}, "model_version": "stage-rules-v1"}
    if context_stage:
        candidates = [{"stage": context_stage, "score": 0.65}, {"stage": "unknown", "score": 0.35}]; confidence = 0.65; status = "context_only"
    elif canopy is not None and float(canopy) < 20: candidates = [{"stage": "emergence", "score": 0.75}, {"stage": "vegetative", "score": 0.25}]; confidence = 0.75; status = "estimated"
    elif canopy is not None and float(canopy) < 70: candidates = [{"stage": "vegetative", "score": 0.7}, {"stage": "reproductive", "score": 0.3}]; confidence = 0.7; status = "estimated"
    else: candidates = [{"stage": "reproductive", "score": 0.6}, {"stage": "senescence", "score": 0.4}]; confidence = 0.6; status = "estimated"
    return {"status": status, "predicted_stage": candidates[0]["stage"], "candidates": candidates, "confidence": confidence, "inputs": {"crop_type": crop_type, **features, "history": history}, "evidence_ids": evidence_ids, "uncertainty": {"method": "interpretable_stage_heuristic", "human_correction_available": True}, "model_version": "stage-rules-v1"}


def forecast_yield(labels: list[dict[str, Any]], *, units: str | None, feature_adjustment: float = 0.0) -> dict[str, Any]:
    usable = [row for row in labels if row.get("yield_value") is not None and (units is None or row.get("yield_unit") == units) and float(row.get("quality", 0)) >= 0.5]
    if len(usable) < 2: return {"status": "not_applicable", "units": units, "forecast_range": {}, "confidence_interval": {}, "confidence": 0.0, "factors": {}, "applicability": {"eligible": False, "reasons": ["minimum_two_quality_harvest_labels_required"], "label_count": len(usable)}, "uncertainty": {"reason": "insufficient_actual_harvest_history"}, "harvest_label_ids": [row.get("id") for row in usable]}
    values = [float(row["yield_value"]) for row in usable]; baseline = mean(values); spread = pstdev(values) if len(values) > 1 else 0.0; adjustment = max(-0.2, min(0.2, float(feature_adjustment))); forecast = baseline * (1.0 + adjustment); margin = max(spread, baseline * 0.1); low = max(0.0, forecast - margin); high = forecast + margin
    return {"status": "pass", "units": units or usable[0].get("yield_unit"), "forecast_range": {"low": low, "expected": forecast, "high": high}, "confidence_interval": {"level": 0.8, "low": low, "high": high}, "confidence": _clamp(0.45 + min(0.35, len(usable) * 0.05) - min(0.2, spread / max(baseline, 1e-9))), "factors": {"historical_mean": baseline, "historical_spread": spread, "feature_adjustment": adjustment}, "applicability": {"eligible": True, "label_count": len(usable), "reasons": []}, "uncertainty": {"method": "historical_range_with_bounded_adjustment", "actual_harvest_labels": len(usable)}, "harvest_label_ids": [row.get("id") for row in usable]}

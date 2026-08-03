"""Calibration-gated vegetation indices, thermal summaries and sensor fusion."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean
from typing import Any, Iterable


def validate_spectral_inputs(bands: Iterable[Any], *, required: set[str] | None = None) -> dict[str, Any]:
    rows = list(bands); names = {str(row.band_name).lower() for row in rows}; required = required or {"red", "nir"}
    reasons: list[str] = []
    missing = sorted(required - names)
    if missing: reasons.append("missing_bands:" + ",".join(missing))
    for row in rows:
        if str(row.band_name).lower() not in required: continue
        if not row.calibration_id: reasons.append(f"missing_calibration:{row.band_name}")
        if row.alignment_status != "pass": reasons.append(f"band_not_aligned:{row.band_name}")
        if row.quality_status != "pass": reasons.append(f"band_quality_not_pass:{row.band_name}")
        if not row.reflectance_panel: reasons.append(f"missing_reflectance_panel:{row.band_name}")
    return {"status": "pass" if not reasons else "blocked", "required_bands": sorted(required), "available_bands": sorted(names), "missing_bands": missing, "failure_reasons": sorted(set(reasons)), "calibration_version": ",".join(sorted({str(row.calibration_id) for row in rows if row.calibration_id})) or None}


def compute_vegetation_index(band_values: dict[str, list[float]], *, index_name: str = "ndvi") -> dict[str, Any]:
    index_name = index_name.lower()
    left_name = "red" if index_name == "ndvi" else "green" if index_name == "gndvi" else None
    if left_name is None: return {"status": "blocked", "reason": "unsupported_index", "index": index_name}
    left = band_values.get(left_name); nir = band_values.get("nir")
    if not left or not nir or len(left) != len(nir): return {"status": "blocked", "reason": "band_values_missing_or_length_mismatch", "index": index_name}
    values = []
    for visible, near_ir in zip(left, nir):
        denominator = float(near_ir) + float(visible)
        values.append((float(near_ir) - float(visible)) / denominator if denominator else 0.0)
    return {"status": "pass", "index": index_name, "values": values, "min": min(values), "max": max(values), "mean": mean(values), "sample_count": len(values), "units": "unitless", "uncertainty": {"method": "band_ratio", "invalid_zero_denominator": sum(1 for value in values if value == 0)}}


def thermal_summary(values: list[float] | None, *, hot_threshold_c: float = 35.0, cool_threshold_c: float = 15.0, calibrated: bool = False) -> dict[str, Any]:
    if not values: return {"status": "not_measured", "reason": "thermal_values_missing", "units": "°C"}
    status = "pass" if calibrated else "blocked"
    return {"status": status, "units": "°C", "min_c": min(values), "max_c": max(values), "mean_c": mean(values), "hot_fraction": sum(value >= hot_threshold_c for value in values) / len(values), "cool_fraction": sum(value <= cool_threshold_c for value in values) / len(values), "sample_count": len(values), "failure_reasons": [] if calibrated else ["thermal_radiometric_calibration_missing"], "uncertainty": {"thresholds_c": {"hot": hot_threshold_c, "cool": cool_threshold_c}, "calibrated": calibrated}}


def sensor_freshness(readings: Iterable[Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC); grouped: dict[str, list[Any]] = {}
    for reading in readings: grouped.setdefault(str(reading.sensor_type), []).append(reading)
    result: dict[str, Any] = {}
    for sensor_type, rows in grouped.items():
        latest = max(rows, key=lambda row: row.timestamp_utc); timestamp = latest.timestamp_utc if latest.timestamp_utc.tzinfo else latest.timestamp_utc.replace(tzinfo=UTC); age = max(0.0, (current - timestamp.astimezone(UTC)).total_seconds()); limit = float(latest.stale_after_seconds or 900.0)
        result[sensor_type] = {"status": "stale" if age > limit else "pass", "age_seconds": age, "stale_after_seconds": limit, "quality": float(latest.quality), "source": latest.source, "timestamp": timestamp.isoformat(), "values": latest.values, "units": latest.units, "reading_id": latest.id}
    return result


def multimodal_risk(*, visual: dict[str, float], thermal: dict[str, Any] | None, sensor_state: dict[str, Any], crop_context: dict[str, Any], history: dict[str, float] | None = None) -> dict[str, Any]:
    factors: dict[str, float] = {}
    if visual.get("canopy_stress") is not None: factors["visual_canopy_stress"] = max(0.0, min(1.0, float(visual["canopy_stress"])))
    if thermal and thermal.get("status") == "pass": factors["thermal_hot_fraction"] = float(thermal.get("hot_fraction", 0.0))
    for sensor_type, state in sensor_state.items():
        if state.get("status") == "pass":
            values = state.get("values", {})
            if sensor_type == "soil_moisture" and values.get("percent") is not None: factors["soil_moisture_stress"] = max(0.0, min(1.0, 1.0 - float(values["percent"]) / 100.0))
            if sensor_type == "humidity" and values.get("percent") is not None: factors["humidity_context"] = max(0.0, min(1.0, float(values["percent"]) / 100.0))
    if history and history.get("stress_delta") is not None: factors["historical_change"] = max(0.0, min(1.0, float(history["stress_delta"])))
    score = sum(factors.values()) / max(1, len(factors)); missing = [key for key in ("thermal", "soil_moisture") if key not in sensor_state or sensor_state[key].get("status") != "pass"]
    confidence = max(0.15, min(0.95, score * (1.0 - 0.15 * len(missing)))) if factors else 0.15
    return {"status": "candidate" if score >= 0.45 else "normal", "suspected_issue": "multimodal_crop_stress_signature" if score >= 0.45 else None, "risk_score": score, "confidence": confidence, "factors": factors, "missing_inputs": missing, "crop_context": {key: crop_context.get(key) for key in ("crop_type", "variety", "growth_stage")}, "explanation": "suspected signature only; not a confirmed disease"}

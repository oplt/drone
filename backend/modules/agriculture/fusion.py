"""Calibration-gated vegetation indices, thermal summaries and sensor fusion."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from math import isfinite
from statistics import mean
from typing import Any

INDEX_SPECS: dict[str, dict[str, Any]] = {
    "ndvi": {"left": "red", "right": "nir", "formula": "(nir-red)/(nir+red)"},
    "gndvi": {"left": "green", "right": "nir", "formula": "(nir-green)/(nir+green)"},
    "ndre": {"left": "red_edge", "right": "nir", "formula": "(nir-red_edge)/(nir+red_edge)"},
}


def sample_feature_collection(
    values: list[float] | None,
    geometries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pair computed samples with available capture geometries."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": geometries[index] if index < len(geometries) else None,
                "properties": {"value": value, "sample_index": index},
            }
            for index, value in enumerate(values or [])
        ],
    }


BAND_WAVELENGTH_RANGES_NM = {
    "blue": (430.0, 510.0),
    "green": (500.0, 600.0),
    "red": (600.0, 720.0),
    "red_edge": (680.0, 760.0),
    "nir": (740.0, 1100.0),
}


def required_bands(index_name: str) -> set[str]:
    spec = INDEX_SPECS.get(index_name.lower())
    return {spec["left"], spec["right"]} if spec else set()


def validate_spectral_inputs(
    bands: Iterable[Any], *, required: set[str] | None = None
) -> dict[str, Any]:
    rows = list(bands)
    names = {str(row.band_name).lower() for row in rows}
    required = required or {"red", "nir"}
    reasons: list[str] = []
    missing = sorted(required - names)
    if missing:
        reasons.append("missing_bands:" + ",".join(missing))
    for row in rows:
        if str(row.band_name).lower() not in required:
            continue
        if not row.calibration_id:
            reasons.append(f"missing_calibration:{row.band_name}")
        if not getattr(row, "sensor_serial", None):
            reasons.append(f"missing_sensor_serial:{row.band_name}")
        wavelength = getattr(row, "wavelength_nm", None)
        if wavelength is None:
            reasons.append(f"missing_wavelength:{row.band_name}")
        else:
            limits = BAND_WAVELENGTH_RANGES_NM.get(str(row.band_name).lower())
            if limits and not limits[0] <= float(wavelength) <= limits[1]:
                reasons.append(f"wavelength_out_of_range:{row.band_name}")
        if row.alignment_status != "pass":
            reasons.append(f"band_not_aligned:{row.band_name}")
        if row.quality_status != "pass":
            reasons.append(f"band_quality_not_pass:{row.band_name}")
        if not row.reflectance_panel:
            reasons.append(f"missing_reflectance_panel:{row.band_name}")
    relevant = [row for row in rows if str(row.band_name).lower() in required]
    return {
        "status": "pass" if not reasons else "blocked",
        "required_bands": sorted(required),
        "available_bands": sorted(names),
        "missing_bands": missing,
        "failure_reasons": sorted(set(reasons)),
        "calibration_version": ",".join(
            sorted({str(row.calibration_id) for row in relevant if row.calibration_id})
        )
        or None,
        "sensor_serials": sorted(
            {str(row.sensor_serial) for row in relevant if getattr(row, "sensor_serial", None)}
        ),
        "band_mapping": {
            name: [
                {
                    "band_id": getattr(row, "id", None),
                    "media_id": getattr(row, "media_id", None),
                    "wavelength_nm": getattr(row, "wavelength_nm", None),
                    "sensor_serial": getattr(row, "sensor_serial", None),
                    "calibration_id": getattr(row, "calibration_id", None),
                }
                for row in relevant
                if str(row.band_name).lower() == name
            ]
            for name in sorted(required)
        },
    }


def compute_vegetation_index(
    band_values: dict[str, list[float]], *, index_name: str = "ndvi"
) -> dict[str, Any]:
    index_name = index_name.lower()
    spec = INDEX_SPECS.get(index_name)
    if spec is None:
        return {"status": "blocked", "reason": "unsupported_index", "index": index_name}
    left_name = str(spec["left"])
    right_name = str(spec["right"])
    left = band_values.get(left_name)
    right = band_values.get(right_name)
    if not left or not right or len(left) != len(right):
        return {
            "status": "blocked",
            "reason": "band_values_missing_or_length_mismatch",
            "index": index_name,
            "required_bands": [left_name, right_name],
        }
    if any(not isfinite(float(value)) or float(value) < 0 for value in [*left, *right]):
        return {"status": "blocked", "reason": "reflectance_values_invalid", "index": index_name}
    values = []
    zero_denominators = 0
    for left_value, right_value in zip(left, right, strict=True):
        denominator = float(right_value) + float(left_value)
        if not denominator:
            zero_denominators += 1
            values.append(0.0)
        else:
            values.append((float(right_value) - float(left_value)) / denominator)
    return {
        "status": "pass",
        "index": index_name,
        "formula": spec["formula"],
        "required_bands": [left_name, right_name],
        "values": values,
        "min": min(values),
        "max": max(values),
        "mean": mean(values),
        "sample_count": len(values),
        "units": "unitless",
        "uncertainty": {
            "method": "calibrated_reflectance_band_ratio",
            "zero_denominator_count": zero_denominators,
        },
    }


def thermal_summary(
    values: list[float] | None,
    *,
    calibrated: bool = False,
    environmental_context: dict[str, Any] | None = None,
    hot_delta_threshold_c: float = 5.0,
    cool_delta_threshold_c: float = -5.0,
) -> dict[str, Any]:
    if not values:
        return {"status": "not_measured", "reason": "thermal_values_missing", "units": "°C"}
    context = dict(environmental_context or {})
    ambient = context.get("ambient_air_temp_c")
    failures = []
    if not calibrated:
        failures.append("thermal_radiometric_calibration_missing")
    if not isinstance(ambient, (int, float)):
        failures.append("ambient_air_temperature_missing")
    if failures:
        return {
            "status": "blocked",
            "units": "°C",
            "sample_count": len(values),
            "failure_reasons": failures,
            "environmental_context": context,
            "uncertainty": {"calibrated": calibrated},
        }
    deltas = [float(value) - float(ambient) for value in values]
    context_warnings = [
        key for key in ("relative_humidity_pct", "wind_speed_mps") if context.get(key) is None
    ]
    return {
        "status": "pass",
        "claim": "thermal_canopy_stress_candidate",
        "units": "°C",
        "min_c": min(values),
        "max_c": max(values),
        "mean_c": mean(values),
        "ambient_air_temp_c": float(ambient),
        "mean_canopy_delta_c": mean(deltas),
        "hot_fraction": sum(value >= hot_delta_threshold_c for value in deltas) / len(deltas),
        "cool_fraction": sum(value <= cool_delta_threshold_c for value in deltas) / len(deltas),
        "sample_count": len(values),
        "failure_reasons": [],
        "environmental_context": context,
        "context_warnings": context_warnings,
        "uncertainty": {
            "delta_thresholds_c": {"hot": hot_delta_threshold_c, "cool": cool_delta_threshold_c},
            "calibrated": True,
            "interpretation": "inspection_candidate_not_disease_diagnosis",
        },
    }


def sensor_freshness(readings: Iterable[Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    grouped: dict[str, list[Any]] = {}
    for reading in readings:
        grouped.setdefault(str(reading.sensor_type), []).append(reading)
    result: dict[str, Any] = {}
    for sensor_type, rows in grouped.items():
        latest = max(rows, key=lambda row: row.timestamp_utc)
        timestamp = (
            latest.timestamp_utc
            if latest.timestamp_utc.tzinfo
            else latest.timestamp_utc.replace(tzinfo=UTC)
        )
        age = max(0.0, (current - timestamp.astimezone(UTC)).total_seconds())
        limit = float(latest.stale_after_seconds or 900.0)
        result[sensor_type] = {
            "status": "stale" if age > limit else "pass",
            "age_seconds": age,
            "stale_after_seconds": limit,
            "quality": float(latest.quality),
            "source": latest.source,
            "timestamp": timestamp.isoformat(),
            "values": latest.values,
            "units": latest.units,
            "reading_id": latest.id,
        }
    return result


def multimodal_risk(
    *,
    visual: dict[str, float],
    thermal: dict[str, Any] | None,
    sensor_state: dict[str, Any],
    crop_context: dict[str, Any],
    history: dict[str, float] | None = None,
) -> dict[str, Any]:
    factors: dict[str, float] = {}
    if visual.get("canopy_stress") is not None:
        factors["visual_canopy_stress"] = max(0.0, min(1.0, float(visual["canopy_stress"])))
    if thermal and thermal.get("status") == "pass":
        factors["thermal_hot_fraction"] = float(thermal.get("hot_fraction", 0.0))
    for sensor_type, state in sensor_state.items():
        if state.get("status") == "pass":
            values = state.get("values", {})
            if sensor_type == "soil_moisture" and values.get("percent") is not None:
                factors["soil_moisture_stress"] = max(
                    0.0, min(1.0, 1.0 - float(values["percent"]) / 100.0)
                )
            if sensor_type == "humidity" and values.get("percent") is not None:
                factors["humidity_context"] = max(0.0, min(1.0, float(values["percent"]) / 100.0))
    if history and history.get("stress_delta") is not None:
        factors["historical_change"] = max(0.0, min(1.0, float(history["stress_delta"])))
    score = sum(factors.values()) / max(1, len(factors))
    missing = []
    if not thermal or thermal.get("status") != "pass":
        missing.append("thermal")
    if "soil_moisture" not in sensor_state or sensor_state["soil_moisture"].get("status") != "pass":
        missing.append("soil_moisture")
    confidence = max(0.15, min(0.95, score * (1.0 - 0.15 * len(missing)))) if factors else 0.15
    return {
        "status": "candidate" if score >= 0.45 else "normal",
        "suspected_issue": "multimodal_crop_stress_signature" if score >= 0.45 else None,
        "risk_score": score,
        "confidence": confidence,
        "factors": factors,
        "missing_inputs": missing,
        "crop_context": {
            key: crop_context.get(key) for key in ("crop_type", "variety", "growth_stage")
        },
        "explanation": "suspected signature only; not a confirmed disease",
    }

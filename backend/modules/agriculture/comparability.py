"""Flight comparability scoring for trustworthy temporal comparison."""

from __future__ import annotations

from typing import Any

COMPARABILITY_POLICY_VERSION = "flight_comparability_v1"
DEFAULT_MIN_COMPARABILITY = 0.45


def _profile(flight: Any) -> dict[str, Any]:
    return dict(getattr(flight, "profile_snapshot", None) or {})


def _quality(flight: Any) -> dict[str, Any]:
    return dict(getattr(flight, "quality_summary", None) or {})


def _models(run: Any | None) -> dict[str, Any]:
    return dict(getattr(run, "model_versions", None) or {}) if run is not None else {}


def _calibration(run: Any | None) -> dict[str, Any]:
    return dict(getattr(run, "calibration_versions", None) or {}) if run is not None else {}


def score_comparability(
    *,
    current: Any,
    reference: Any,
    current_run: Any | None = None,
    reference_run: Any | None = None,
    alignment: dict[str, Any] | None = None,
    min_quality_score: float = 0.6,
) -> dict[str, Any]:
    """Score whether two flights can be compared without silently mixing incompatible inputs."""
    factors: dict[str, Any] = {}
    warnings: list[str] = []
    blockers: list[str] = []

    if getattr(current, "field_id", None) != getattr(reference, "field_id", None):
        blockers.append("different_field")

    current_profile = _profile(current)
    reference_profile = _profile(reference)
    current_quality = _quality(current)
    reference_quality = _quality(reference)
    current_models = _models(current_run)
    reference_models = _models(reference_run)
    current_cal = _calibration(current_run)
    reference_cal = _calibration(reference_run)

    # Geometry / footprint overlap from alignment metrics when available.
    overlap = float((alignment or {}).get("alignment_score") or (alignment or {}).get("overlap_pct", 0) / 100 or 0.0)
    if alignment and alignment.get("status") == "failed":
        blockers.append("alignment_failed")
        geometry_factor = 0.0
    elif alignment and alignment.get("status") == "low_confidence":
        warnings.append("low_spatial_overlap")
        geometry_factor = max(0.2, overlap)
    else:
        geometry_factor = overlap if alignment else 0.6
    factors["geometry"] = {"factor": round(geometry_factor, 4), "overlap": round(overlap, 4), "weight": 0.25}

    crop_match = (
        not current_profile.get("crop_type")
        or current_profile.get("crop_type") == reference_profile.get("crop_type")
    )
    season_match = (
        not getattr(current, "season", None)
        or getattr(current, "season", None) == getattr(reference, "season", None)
        or current_profile.get("season") == reference_profile.get("season")
    )
    growth_match = (
        not current_profile.get("growth_stage")
        or current_profile.get("growth_stage") == reference_profile.get("growth_stage")
    )
    if not crop_match:
        blockers.append("crop_type_mismatch")
    if not season_match:
        warnings.append("season_mismatch")
    if not growth_match:
        warnings.append("growth_stage_mismatch")
    crop_factor = (1.0 if crop_match else 0.0) * (0.85 if season_match else 0.55) * (0.9 if growth_match else 0.7)
    factors["season_crop"] = {
        "factor": round(crop_factor, 4),
        "crop_match": crop_match,
        "season_match": season_match,
        "growth_stage_match": growth_match,
        "weight": 0.2,
    }

    sensor_match = (
        not current_profile.get("sensor_inventory")
        or current_profile.get("sensor_inventory") == reference_profile.get("sensor_inventory")
    )
    if not sensor_match:
        blockers.append("sensor_inventory_mismatch")
    factors["sensor"] = {"factor": 1.0 if sensor_match else 0.0, "match": sensor_match, "weight": 0.15}

    current_score = float(current_quality.get("score", 0.0) or 0.0)
    reference_score = float(reference_quality.get("score", 0.0) or 0.0)
    current_status = current_quality.get("status")
    reference_status = reference_quality.get("status")
    quality_ok = (
        current_status in {"pass", "warning", None}
        and reference_status in {"pass", "warning", None}
        and current_score >= min_quality_score
        and reference_score >= min_quality_score
    )
    if current_status not in {"pass", "warning", None} or reference_status not in {"pass", "warning", None}:
        blockers.append("capture_quality_failed")
    elif not quality_ok:
        warnings.append("capture_quality_below_threshold")
    quality_factor = min(current_score, reference_score) if quality_ok else min(0.4, min(current_score, reference_score))
    factors["capture_quality"] = {
        "factor": round(float(quality_factor), 4),
        "current_score": current_score,
        "reference_score": reference_score,
        "weight": 0.15,
    }

    model_match = current_models == reference_models or (not current_models and not reference_models)
    if current_models and reference_models and current_models != reference_models:
        blockers.append("model_release_mismatch")
        warnings.append("model_versions_changed")
    elif current_models != reference_models:
        warnings.append("model_versions_incomplete")
    factors["model_release"] = {
        "factor": 1.0 if model_match else 0.0,
        "match": model_match,
        "current": current_models,
        "reference": reference_models,
        "weight": 0.15,
    }

    cal_match = current_cal == reference_cal or (not current_cal and not reference_cal)
    if current_cal and reference_cal and current_cal != reference_cal:
        blockers.append("calibration_mismatch")
        warnings.append("calibration_changed")
    factors["calibration"] = {
        "factor": 1.0 if cal_match else 0.0,
        "match": cal_match,
        "current": current_cal,
        "reference": reference_cal,
        "weight": 0.05,
    }

    telemetry_ok = True
    for flight, quality in ((current, current_quality), (reference, reference_quality)):
        if quality.get("telemetry_status") in {"failed", "missing"}:
            telemetry_ok = False
            warnings.append("telemetry_quality_degraded")
            break
        gap_count = int((getattr(flight, "input_manifest", None) or {}).get("telemetry_gap_count") or 0)
        if gap_count > 0:
            warnings.append("telemetry_gaps_present")
            telemetry_ok = False
            break
    factors["telemetry"] = {"factor": 1.0 if telemetry_ok else 0.55, "ok": telemetry_ok, "weight": 0.05}

    score = (
        0.25 * float(factors["geometry"]["factor"])
        + 0.2 * float(factors["season_crop"]["factor"])
        + 0.15 * float(factors["sensor"]["factor"])
        + 0.15 * float(factors["capture_quality"]["factor"])
        + 0.15 * float(factors["model_release"]["factor"])
        + 0.05 * float(factors["calibration"]["factor"])
        + 0.05 * float(factors["telemetry"]["factor"])
    )
    eligible = not blockers and score >= DEFAULT_MIN_COMPARABILITY
    status = "eligible" if eligible else ("incompatible" if blockers else "low_confidence")
    return {
        "policy_version": COMPARABILITY_POLICY_VERSION,
        "score": round(float(score), 4),
        "eligible": eligible,
        "status": status,
        "factors": factors,
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
        "min_comparability": DEFAULT_MIN_COMPARABILITY,
    }

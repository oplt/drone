from types import SimpleNamespace

from backend.modules.agriculture.crop_insights import build_crop_risks, estimate_growth_stage, forecast_yield, model_applicability, summarize_growth


def test_crop_specific_model_requires_deployment_validation_and_holdout_fields():
    model = SimpleNamespace(status="deployed", version="tomato-risk-v1", config={"crop_types": ["tomato"]})
    report = SimpleNamespace(id="report-1", metrics={"f1": .82, "holdout_field_count": 4, "calibration_mae": .1}, drift={"status": "pass"})
    assert model_applicability(model, [report], task="crop_risk", crop_type="tomato", growth_stage="vegetative")["eligible"]
    assert not model_applicability(model, [], task="crop_risk", crop_type="tomato", growth_stage="vegetative")["eligible"]


def test_unvalidated_crop_risk_emits_signature_not_disease_claim():
    result = build_crop_risks(visual={"canopy_stress": .8}, fusion={}, thermal={}, sensors={}, crop_type="wheat", growth_stage="vegetative", history={}, geometry={"type": "Point", "coordinates": [4, 50]}, evidence_ids=["frame-1"], applicability={"eligible": False, "reasons": ["no_model_registered"]})[0]
    assert result["issue_type"] == "crop_stress_signature"
    assert "not a confirmed disease" in result["uncertainty"]["policy"]
    assert result["inspection_points"]


def test_growth_summary_reports_range_uniformity_and_trend():
    result = summarize_growth([1, 2, 3, 4], units="m", source_kind="lidar", previous_mean=1)
    assert result["status"] == "pass"
    assert result["summary"]["p10"] == 1
    assert result["summary"]["trend"] == "increasing"
    assert 0 <= result["summary"]["uniformity_score"] <= 1


def test_growth_stage_uses_context_and_allows_human_correction():
    result = estimate_growth_stage(crop_type="corn", context_stage="vegetative", features={}, history=[], evidence_ids=[])
    assert result["status"] == "context_only"
    assert result["predicted_stage"] == "vegetative"
    assert result["uncertainty"]["human_correction_available"]


def test_yield_requires_quality_actual_harvest_labels_and_returns_interval():
    labels = [{"id": "h1", "yield_value": 8, "yield_unit": "t/ha", "quality": .9}, {"id": "h2", "yield_value": 10, "yield_unit": "t/ha", "quality": .9}]
    result = forecast_yield(labels, units="t/ha")
    assert result["status"] == "pass"
    assert result["forecast_range"]["low"] <= result["forecast_range"]["expected"] <= result["forecast_range"]["high"]
    assert result["confidence_interval"]["level"] == .8

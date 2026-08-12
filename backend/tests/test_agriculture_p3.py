from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

from backend.modules.agriculture.fusion import compute_vegetation_index, multimodal_risk, sensor_freshness, thermal_summary, validate_spectral_inputs
from backend.modules.agriculture.rgb_products import evaluate_rgb_products, product_gate_summary


def _band(name, calibration_id="cal-1", alignment_status="pass", quality_status="pass", panel=True):
    return SimpleNamespace(band_name=name, calibration_id=calibration_id, alignment_status=alignment_status, quality_status=quality_status, reflectance_panel={"reference": 1} if panel else {})


def test_ndvi_requires_calibrated_aligned_red_and_nir():
    assert validate_spectral_inputs([_band("red"), _band("nir")])["status"] == "pass"
    blocked = validate_spectral_inputs([_band("red"), _band("nir", alignment_status="failed")])
    assert blocked["status"] == "blocked"
    assert "band_not_aligned:nir" in blocked["failure_reasons"]


def test_rgb_cannot_become_ndvi_and_calibrated_index_is_auditable():
    assert abs(compute_vegetation_index({"red": [0.2], "nir": [0.8]})["values"][0] - .6) < 1e-9
    assert compute_vegetation_index({"rgb": [0.2]})["status"] == "blocked"


def test_thermal_without_radiometric_calibration_is_not_measured():
    assert thermal_summary([20, 40], calibrated=False)["status"] == "blocked"
    assert thermal_summary([], calibrated=True)["status"] == "not_measured"


def test_stale_sensor_reduces_multimodal_confidence_and_explains_gap():
    reading = SimpleNamespace(sensor_type="soil_moisture", timestamp_utc=datetime.now(UTC) - timedelta(hours=2), stale_after_seconds=60, quality=.9, source="iot", values={"percent": 20}, units={"percent": "%"}, id="r1")
    state = sensor_freshness([reading])
    risk = multimodal_risk(visual={"canopy_stress": .8}, thermal=None, sensor_state=state, crop_context={}, history={})
    assert state["soil_moisture"]["status"] == "stale"
    assert "soil_moisture" in risk["missing_inputs"]
    assert risk["explanation"].endswith("not a confirmed disease")


def test_rgb_products_are_explicit_candidate_only_and_quality_aware():
    products = evaluate_rgb_products(
        segmentation={"canopy_pct": 42.0, "visible_water_pct": 2.0},
        row={"confidence": 0.72},
        quality={"status": "pass"},
        requested=["canopy_cover", "standing_water", "row_detection"],
    )
    assert set(products) == {"canopy_cover", "row_detection", "standing_water"}
    gated = product_gate_summary(products)
    assert all(item["claim_status"] == "candidate" for item in gated.values())
    assert all(item["publishable"] is False for item in gated.values())
    assert all(item["model_gate"] == "candidate_only" for item in gated.values())


def test_rgb_products_block_when_quality_gate_fails():
    products = evaluate_rgb_products(
        segmentation={"canopy_pct": 42.0},
        row={"confidence": 0.72},
        quality={"status": "blocked"},
        requested=["canopy_cover", "row_detection"],
    )
    assert {item["status"] for item in products.values()} == {"blocked_quality"}

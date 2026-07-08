from types import SimpleNamespace

import pytest

from backend.modules.warehouse.models import (
    WarehouseLayoutCandidate,
    WarehouseScanArtifactSet,
)
from backend.modules.warehouse.service.scan_to_layout import (
    candidate_status,
    displacement_m,
    extraction_confidence,
    geometry_anchor,
    review_reasons,
)


def test_displacement_review_uses_metric_geometry_anchor() -> None:
    reference = {"target_point": {"x_m": 1.0, "y_m": 2.0, "z_m": 3.0}}
    observed = {"target_point": {"x_m": 1.3, "y_m": 2.4, "z_m": 3.0}}

    assert geometry_anchor(reference) == (1.0, 2.0, 3.0)
    assert displacement_m(reference, observed) == pytest.approx(0.5)
    assert candidate_status(displacement=0.5, threshold_m=0.25) == "needs_review"
    assert candidate_status(displacement=0.1, threshold_m=0.25) == "provisional"


def test_candidate_review_reasons_capture_manual_confirmation_rules() -> None:
    geometry = {
        "evidence": {"occupancy_available": False, "esdf_available": False},
        "template": {"bin_count": 4},
        "observed_bin_count": 3,
    }

    reasons = review_reasons(
        entity_kind="rack",
        confidence=0.7,
        geometry=geometry,
        displacement=0.5,
    )

    assert "large_displacement" in reasons
    assert "low_confidence" in reasons
    assert "missing_esdf_or_occupancy_evidence" in reasons
    assert "bin_count_mismatch_vs_template" in reasons
    assert "new_rack_row" not in reasons


def test_new_rack_candidate_requires_review_without_reference() -> None:
    assert candidate_status(
        entity_kind="rack",
        confidence=0.95,
        geometry={},
        displacement=None,
    ) == "needs_review"


def test_extraction_confidence_falls_back_to_clearance_state() -> None:
    assert extraction_confidence(SimpleNamespace(clearance_status="active")) == 0.9
    assert extraction_confidence(SimpleNamespace(clearance_status="needs_review")) == 0.55
    assert extraction_confidence(SimpleNamespace(confidence=2.0)) == 1.0


def test_scan_layout_schema_pins_calibration_and_candidate_review() -> None:
    assert "sensor_rig_id" in WarehouseScanArtifactSet.__table__.columns
    assert "calibration_hash" in WarehouseScanArtifactSet.__table__.columns
    assert "displacement_m" in WarehouseLayoutCandidate.__table__.columns
    assert "confidence" in WarehouseLayoutCandidate.__table__.columns

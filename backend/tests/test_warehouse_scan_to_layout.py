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
)


def test_displacement_review_uses_metric_geometry_anchor() -> None:
    reference = {"target_point": {"x_m": 1.0, "y_m": 2.0, "z_m": 3.0}}
    observed = {"target_point": {"x_m": 1.3, "y_m": 2.4, "z_m": 3.0}}

    assert geometry_anchor(reference) == (1.0, 2.0, 3.0)
    assert displacement_m(reference, observed) == pytest.approx(0.5)
    assert candidate_status(displacement=0.5, threshold_m=0.25) == "needs_review"
    assert candidate_status(displacement=0.1, threshold_m=0.25) == "provisional"


def test_extraction_confidence_falls_back_to_clearance_state() -> None:
    assert extraction_confidence(SimpleNamespace(clearance_status="active")) == 0.9
    assert extraction_confidence(SimpleNamespace(clearance_status="needs_review")) == 0.55
    assert extraction_confidence(SimpleNamespace(confidence=2.0)) == 1.0


def test_scan_layout_schema_pins_calibration_and_candidate_review() -> None:
    assert "sensor_rig_id" in WarehouseScanArtifactSet.__table__.columns
    assert "calibration_hash" in WarehouseScanArtifactSet.__table__.columns
    assert "displacement_m" in WarehouseLayoutCandidate.__table__.columns
    assert "confidence" in WarehouseLayoutCandidate.__table__.columns

"""Static gates ensuring P4 research outcomes stay out of production capability labels."""

from __future__ import annotations

import json
from pathlib import Path

from backend.modules.agriculture.capabilities import CAPABILITIES, default_inference_profile

ROOT = Path(__file__).resolve().parents[2]


def test_no_multispectral_or_prescription_production_capabilities():
    banned = {
        "multispectral",
        "multispectral_stress",
        "ndvi",
        "prescription",
        "prescription_zones",
        "thermal_water_stress",
    }
    assert banned.isdisjoint(CAPABILITIES.keys())


def test_readiness_marks_research_blocked_capabilities():
    readiness = json.loads(
        (ROOT / "backend/modules/agriculture/readiness.json").read_text(encoding="utf-8")
    )
    for priority in ("P1", "P2", "P3"):
        entry = readiness["priorities"][priority]
        assert entry.get("availability") == "research_blocked", priority


def test_stand_count_default_profile_is_standard_baseline():
    profile = default_inference_profile("stand_count")
    assert profile["sahi_enabled"] is False
    assert profile["tracking_enabled"] is False
    weed = default_inference_profile("weed_detection")
    assert weed["sahi_enabled"] is False

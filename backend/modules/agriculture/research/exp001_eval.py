"""Offline EXP-001 spectral / prescription / export evaluation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.modules.agriculture.fusion import compute_vegetation_index, validate_spectral_inputs
from backend.modules.agriculture.p5_policy import build_shapefile_zip

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "benchmarks"
    / "exp001"
    / "fixtures"
)


def load_json(name: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / name
    return json.loads(path.read_text(encoding="utf-8"))


def band_rows(payload: dict[str, Any]) -> list[SimpleNamespace]:
    return [SimpleNamespace(**row) for row in payload["bands"]]


def evaluate_spectral_repeatability() -> dict[str, Any]:
    blocked = validate_spectral_inputs(band_rows(load_json("spectral/bands_missing_panel.json")))
    assert blocked["status"] == "blocked"
    assert any("missing_reflectance_panel" in reason for reason in blocked["failure_reasons"])

    ok_bands = load_json("spectral/bands_calibrated.json")
    gate = validate_spectral_inputs(band_rows(ok_bands))
    assert gate["status"] == "pass"

    values = load_json("spectral/sample_band_values.json")
    first = compute_vegetation_index(values["bands"], index_name="ndvi")
    second = compute_vegetation_index(values["bands"], index_name="ndvi")
    assert first["status"] == "pass"
    assert first["values"] == second["values"]
    golden_mean = float(values["golden"]["ndvi_mean"])
    assert abs(float(first["mean"]) - golden_mean) <= 0.01

    gndvi = compute_vegetation_index(values["bands"], index_name="gndvi")
    assert gndvi["status"] == "pass"
    return {
        "blocked_gate": blocked,
        "pass_gate": gate,
        "ndvi": {"mean": first["mean"], "sample_count": first["sample_count"]},
        "gndvi": {"mean": gndvi["mean"], "sample_count": gndvi["sample_count"]},
        "repeatable": True,
    }


def evaluate_prescription_safety() -> dict[str, Any]:
    """Evaluate prescription constraint logic without DB (mirrors p5_service rules)."""
    rule = load_json("prescription/agronomy_rule.inspection_only.json")
    risks = load_json("prescription/confirmed_risks.json")["risks"]

    def draft_for(rule_payload: dict[str, Any] | None, risk_rows: list[dict[str, Any]]) -> dict[str, Any]:
        blocked: list[str] = []
        if rule_payload is None:
            blocked.append("approved_rule_required")
        elif rule_payload.get("status") != "approved":
            blocked.append("rule_not_approved")
        elif rule_payload.get("action_kind") != "inspection_only" and not rule_payload.get("regulatory_reference"):
            blocked.append("regulatory_reference_required_for_regulated_action")
        if not risk_rows:
            blocked.append("no_confirmed_multimodal_observations")
        zones = []
        if not blocked and rule_payload is not None:
            for risk in risk_rows:
                zones.append(
                    {
                        "type": "Feature",
                        "geometry": risk["geometry"],
                        "properties": {
                            "source_id": risk["id"],
                            "issue_type": risk["issue_type"],
                            "confidence": risk["confidence"],
                            "severity": risk["severity"],
                            "action_kind": rule_payload["action_kind"],
                            "rule_key": rule_payload["rule_key"],
                        },
                    }
                )
        assumptions = ["Only confirmed multimodal observations are eligible", "No chemical or fertilizer rate is generated"]
        return {
            "status": "blocked" if blocked else "draft",
            "zones": zones,
            "assumptions": assumptions + blocked,
            "blocked_reasons": blocked,
        }

    without_rule = draft_for(None, risks)
    with_rule = draft_for(rule, risks)
    regulated = draft_for({**rule, "action_kind": "chemical", "regulatory_reference": None}, risks)
    assert without_rule["status"] == "blocked"
    assert with_rule["status"] == "draft"
    assert with_rule["zones"]
    assert "No chemical or fertilizer rate is generated" in with_rule["assumptions"]
    assert regulated["status"] == "blocked"
    return {
        "without_rule": without_rule["status"],
        "with_inspection_rule": with_rule["status"],
        "zone_count": len(with_rule["zones"]),
        "regulated_without_reference": regulated["blocked_reasons"],
    }


def evaluate_export_conformance() -> dict[str, Any]:
    payload = load_json("machine_export/shapefile_payload.json")
    blob = build_shapefile_zip(payload)
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = set(archive.namelist())
        prj = archive.read("agriculture.prj").decode()
    expected = {"agriculture.shp", "agriculture.shx", "agriculture.dbf", "agriculture.prj"}
    assert expected.issubset(names)
    assert "WGS 84" in prj or "4326" in prj
    isoxml_notes = (FIXTURE_ROOT / "machine_export" / "isoxml_gap.md").read_text(encoding="utf-8")
    assert "NOT VALIDATED" in isoxml_notes
    return {
        "shapefile_members": sorted(names),
        "crs_ok": True,
        "feature_count": len(payload["features"]),
        "isoxml_status": "not_validated",
    }


def run_all() -> dict[str, Any]:
    return {
        "experiment": "EXP-001",
        "spectral": evaluate_spectral_repeatability(),
        "prescription": evaluate_prescription_safety(),
        "export": evaluate_export_conformance(),
        "adr_recommendation": "NO-GO_production_capability",
    }

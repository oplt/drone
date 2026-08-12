"""EXP-001 offline research suite — spectral, prescription, export gates."""

from backend.modules.agriculture.research.exp001_eval import run_all


def test_exp001_research_suite_passes_and_recommends_no_go():
    report = run_all()
    assert report["spectral"]["repeatable"] is True
    assert report["prescription"]["with_inspection_rule"] == "draft"
    assert report["prescription"]["without_rule"] == "blocked"
    assert report["export"]["crs_ok"] is True
    assert report["export"]["isoxml_status"] == "not_validated"
    assert report["adr_recommendation"] == "NO-GO_production_capability"

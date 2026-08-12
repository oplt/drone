"""EXP-002 offline research suite — stand count profile gates."""

from backend.modules.agriculture.research.exp002_eval import evaluate_detector_profiles


def test_exp002_stand_count_profiles_do_not_promote_sahi_default():
    report = evaluate_detector_profiles()
    by_id = {row["profile_id"]: row for row in report["profiles"]}
    assert by_id["A"]["passed"] is True
    assert by_id["D"]["passed"] is False
    assert "count_error" in by_id["D"]["failures"] or "fragmentation_ratio" in by_id["D"]["failures"]
    assert report["promoted_profile_id"] is None
    assert report["adr_recommendation"] == "NO-GO_promotion"
    assert report["default_recommendation"] == "A"

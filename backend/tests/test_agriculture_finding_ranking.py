"""Unit tests for PROD-001 finding ranking policy."""

from types import SimpleNamespace

from backend.modules.agriculture.finding_ranking import (
    RANKING_POLICY_VERSION,
    rank_findings,
    score_finding,
)


def _obs(**overrides):
    base = dict(
        id="obs-1",
        observation_type="weed_detection",
        severity=0.9,
        confidence=0.8,
        area_m2=100.0,
        evidence_ids=["e1", "e2"],
        georef_status="resolved",
        review_state="unreviewed",
        trend="new",
        geometry_geojson={"type": "Point", "coordinates": [4.0, 50.0]},
        provenance={},
        model_version="m1",
        assigned_to_user_id=None,
        merged_into_id=None,
        member_observation_ids=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_ranking_policy_version_and_factor_breakdown():
    scored = score_finding(_obs(), change_state="expanding", crop_context={"crop_type": "maize"})
    assert scored["policy_version"] == RANKING_POLICY_VERSION
    assert scored["display_status"] == "shown"
    assert "severity" in scored["factors"]
    assert "confidence" in scored["factors"]
    assert scored["factors"]["novelty"]["state"] == "expanding"
    assert scored["score"] > 0.4


def test_low_confidence_labeled_and_withheld():
    labeled = score_finding(_obs(confidence=0.2, georef_status="low_confidence"))
    assert labeled["display_status"] == "labeled_low_confidence"
    withheld = score_finding(_obs(confidence=0.05))
    assert withheld["display_status"] == "withheld"
    assert withheld["score"] == 0.0


def test_rank_findings_bounds_and_excludes_merged():
    rows = [
        _obs(id="a", severity=0.95, confidence=0.9),
        _obs(id="b", severity=0.5, confidence=0.7),
        _obs(id="c", severity=0.99, confidence=0.99, merged_into_id="a"),
        _obs(id="d", severity=0.1, confidence=0.05),
    ]
    ranked = rank_findings(rows, limit=2)
    assert len(ranked) == 2
    assert ranked[0]["rank"] == 1
    assert ranked[0]["finding_id"] == "a"
    assert all(item["finding_id"] != "c" for item in ranked)
    assert all(item["finding_id"] != "d" for item in ranked)


def test_rejected_observations_withheld_from_default_queue():
    ranked = rank_findings([_obs(id="r", review_state="rejected")], limit=10)
    assert ranked == []

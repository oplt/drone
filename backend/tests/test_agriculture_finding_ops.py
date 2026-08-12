"""Unit tests for finding merge/split helpers."""

from types import SimpleNamespace

from backend.modules.agriculture.finding_ops import merge_observations, split_observation


def _obs(**overrides):
    base = dict(
        id="primary",
        run_id="run-1",
        flight_id="flight-1",
        field_id=1,
        observation_type="weed_detection",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[[0, 0], [0.002, 0], [0.002, 0.002], [0, 0], [0, 0]]],
        },
        zone_kind="observation",
        georef_status="resolved",
        area_m2=40.0,
        severity=0.6,
        confidence=0.7,
        uncertainty={},
        provenance={},
        first_detected=None,
        last_detected=None,
        trend="new",
        evidence_ids=["e1"],
        sensor_values={},
        model_version="m1",
        review_state="unreviewed",
        review_note=None,
        reviewed_at=None,
        merged_into_id=None,
        split_from_id=None,
        member_observation_ids=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_merge_observations_unions_evidence_and_marks_members():
    primary = _obs()
    member = _obs(id="member", severity=0.9, confidence=0.8, evidence_ids=["e2"], area_m2=10.0)
    merge_observations(primary, [member])
    assert member.merged_into_id == "primary"
    assert member.review_state == "rejected"
    assert "e1" in primary.evidence_ids and "e2" in primary.evidence_ids
    assert "member" in primary.member_observation_ids
    assert primary.severity == 0.9


def test_split_observation_retains_source_provenance():
    source = _obs(id="source", evidence_ids=["a", "b"])
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return f"part-{counter['n']}"

    created = split_observation(
        source,
        [
            {"geometry_geojson": source.geometry_geojson, "evidence_ids": ["a"]},
            {"geometry_geojson": source.geometry_geojson, "evidence_ids": ["b"]},
        ],
        new_id_factory=factory,
    )
    assert len(created) == 2
    assert created[0].split_from_id == "source"
    assert created[1].evidence_ids == ["b"]
    assert source.provenance["split_into_ids"] == ["part-1", "part-2"]

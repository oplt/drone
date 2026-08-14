from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from shapely.geometry import shape

from backend.entrypoints.api.app import app
from backend.modules.agriculture.intervention_exports import (
    build_intervention_zone_export,
    filter_intervention_zones_by_current_sources,
)
from backend.modules.agriculture.intervention_schemas import (
    InterventionZoneApprovalIn,
    InterventionZoneCreateIn,
)
from backend.modules.agriculture.intervention_service import (
    InterventionZoneConflict,
    agriculture_intervention_zone_service,
    normalized_zone_geometry,
    zone_area_m2,
)
from backend.modules.agriculture.schemas import ExportIn


def test_intervention_zone_workflow_and_export_routes_are_published():
    paths = app.openapi()["paths"]
    assert "/agriculture/analysis-runs/{run_id}/intervention-zones" in paths
    assert "/agriculture/intervention-zones/{zone_id}" in paths
    assert "/agriculture/intervention-zones/{zone_id}/approval" in paths
    assert "/agriculture/intervention-zones/{zone_id}/audit" in paths
    assert ExportIn(artifact_kind="intervention_zones", format="geojson")


def test_intervention_zone_geometry_requires_valid_area_polygon():
    polygon = normalized_zone_geometry(
        {
            "type": "Polygon",
            "coordinates": [[[4.0, 50.0], [4.001, 50.0], [4.001, 50.001], [4.0, 50.0]]],
        }
    )
    assert polygon.geom_type == "Polygon"
    assert zone_area_m2(polygon) > 0

    with pytest.raises(ValueError, match="polygon_required"):
        normalized_zone_geometry({"type": "Point", "coordinates": [4.0, 50.0]})


def test_intervention_zone_contract_rejects_blank_names_and_review_rationale():
    with pytest.raises(ValidationError):
        InterventionZoneCreateIn(
            name="   ", category="scouting", source_observation_ids=["obs-1"]
        )
    with pytest.raises(ValidationError):
        InterventionZoneApprovalIn(status="approved", note="   ", expected_revision=1)


def test_intervention_zone_geometry_repairs_self_intersection_without_inventing_location():
    repaired = normalized_zone_geometry(
        {
            "type": "Polygon",
            "coordinates": [
                [[4.0, 50.0], [4.001, 50.001], [4.001, 50.0], [4.0, 50.001], [4.0, 50.0]]
            ],
        }
    )
    assert repaired.is_valid
    assert shape(repaired.__geo_interface__).bounds == repaired.bounds


@pytest.mark.asyncio
async def test_intervention_zone_review_rejects_stale_revision_before_operational_change():
    zone = SimpleNamespace(status="proposed", revision=3)
    with pytest.raises(InterventionZoneConflict, match="revision_conflict"):
        await agriculture_intervention_zone_service.review(
            SimpleNamespace(),
            zone=zone,
            status="approved",
            note="Field lead reviewed the geometry",
            expected_revision=2,
            user_id=7,
        )
    assert zone.status == "proposed"


def test_intervention_zone_export_requires_approval_and_records_lineage():
    zone = SimpleNamespace(
        id="zone-1",
        status="approved",
        name="North weeds",
        category="weed_control",
        area_m2=42.0,
        geometry_geojson={"type": "Polygon", "coordinates": []},
        source_observation_ids=["obs-1"],
        evidence_ids=["frame-1"],
        model_versions=["weed-v2"],
        reviewed_by_user_id=7,
        reviewed_at=datetime.now(UTC),
        run_id="run-1",
    )
    source_ids, features, metadata = build_intervention_zone_export([zone])
    assert source_ids == ["zone-1", "obs-1"]
    assert features[0]["properties"]["source_run_id"] == "run-1"
    assert metadata["source_models"] == ["weed-v2"]
    assert metadata["reviewer_user_ids"] == [7]

    zone.status = "rejected"
    with pytest.raises(ValueError, match="approved_intervention_zone_required"):
        build_intervention_zone_export([zone])


def test_intervention_zone_export_excludes_zones_with_stale_source_reviews():
    current = SimpleNamespace(
        id="zone-current", source_observation_ids=["obs-confirmed"]
    )
    stale = SimpleNamespace(
        id="zone-stale", source_observation_ids=["obs-rejected"]
    )
    observations = [
        SimpleNamespace(
            id="obs-confirmed",
            run_id="run-1",
            review_state="confirmed",
            merged_into_id=None,
        ),
        SimpleNamespace(
            id="obs-rejected",
            run_id="run-1",
            review_state="rejected",
            merged_into_id=None,
        ),
    ]
    eligible, excluded = filter_intervention_zones_by_current_sources(
        [current, stale], observations, run_id="run-1"
    )
    assert eligible == [current]
    assert excluded == ["zone-stale"]

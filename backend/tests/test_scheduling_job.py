from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.modules.automation.scheduling_job import _mission_payload


def test_mission_payload_adds_template_identity() -> None:
    template = SimpleNamespace(
        name="North field",
        mission_type="waypoint",
        config={
            "cruise_alt": 30,
            "waypoints": [
                {"lat": 50.0, "lon": 4.0, "alt": 30},
                {"lat": 50.001, "lon": 4.001, "alt": 30},
            ],
        },
    )

    payload = _mission_payload(template)

    assert payload.name == "North field"
    assert payload.mission_type.value == "waypoint"


def test_mission_payload_rejects_invalid_template_config() -> None:
    template = SimpleNamespace(
        name="Broken grid",
        mission_type="grid",
        config={"cruise_alt": 30},
    )

    with pytest.raises(ValidationError):
        _mission_payload(template)

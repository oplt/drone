from __future__ import annotations

import pytest

from backend.modules.mapping.api.mapping_route_schemas import MappingJobCreateIn


def test_mapping_job_create_rejects_upload_with_immediate_start() -> None:
    with pytest.raises(ValueError, match="start_immediately=false"):
        MappingJobCreateIn.model_validate(
            {
                "field_id": 1,
                "input_source": "upload",
                "start_immediately": True,
            }
        )


def test_mapping_job_create_rejects_drone_sync_without_immediate_start() -> None:
    with pytest.raises(ValueError, match="start_immediately=true"):
        MappingJobCreateIn.model_validate(
            {
                "field_id": 1,
                "input_source": "drone_sync",
                "start_immediately": False,
            }
        )


def test_mapping_job_create_accepts_upload_staged_flow() -> None:
    payload = MappingJobCreateIn.model_validate(
        {
            "field_id": 1,
            "input_source": "upload",
            "start_immediately": False,
        }
    )
    assert payload.input_source == "upload"
    assert payload.start_immediately is False

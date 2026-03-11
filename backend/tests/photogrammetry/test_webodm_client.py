from __future__ import annotations

import json

from backend.services.photogrammetry.webodm_client import WebODMClient


def test_nodeodm_options_payload_converts_dict_to_option_array() -> None:
    payload = WebODMClient._nodeodm_options_payload(  # type: ignore[attr-defined]
        {
            "auto-boundary": True,
            "dem-resolution": 10,
            "feature-quality": "medium",
            "skip-report": None,
        }
    )

    assert json.loads(payload) == [
        {"name": "auto-boundary", "value": True},
        {"name": "dem-resolution", "value": 10},
        {"name": "feature-quality", "value": "medium"},
    ]


def test_token_shape_helpers_distinguish_jwt_from_nodeodm_uuid() -> None:
    assert WebODMClient._looks_like_uuid_token("7e88b185-f887-4316-bfa6-7fb7d8153637")  # type: ignore[attr-defined]
    assert not WebODMClient._looks_like_jwt_token("7e88b185-f887-4316-bfa6-7fb7d8153637")  # type: ignore[attr-defined]
    assert WebODMClient._looks_like_jwt_token("aaa.bbb.ccc")  # type: ignore[attr-defined]
    assert not WebODMClient._looks_like_uuid_token("aaa.bbb.ccc")  # type: ignore[attr-defined]


def test_status_code_reads_nested_nodeodm_status_object() -> None:
    assert WebODMClient._status_code({"code": 20}) == 20  # type: ignore[attr-defined]


def test_normalize_task_status_maps_nodeodm_running_payload() -> None:
    payload = {
        "status": {"code": 20},
        "progress": 37,
    }

    assert WebODMClient._normalize_task_status(payload) == {  # type: ignore[attr-defined]
        "state": "RUNNING",
        "progress": 37,
    }


def test_normalize_task_status_maps_failed_payload_error() -> None:
    payload = {
        "status": {"code": 30},
        "progress": 81,
        "error": "boom",
    }

    assert WebODMClient._normalize_task_status(payload) == {  # type: ignore[attr-defined]
        "state": "FAILED",
        "progress": 81,
        "error": "boom",
    }

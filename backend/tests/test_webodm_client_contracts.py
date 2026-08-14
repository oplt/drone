from __future__ import annotations

import httpx

from backend.infrastructure.photogrammetry.webodm_client import WebODMClient


def test_normalize_task_status_completed() -> None:
    result = WebODMClient._normalize_task_status({"status": 40, "running_progress": 100})
    assert result == {"state": "COMPLETED", "progress": 100}


def test_normalize_task_status_failed_includes_error() -> None:
    result = WebODMClient._normalize_task_status(
        {"status": "failed", "error": "processing failed"}
    )
    assert result["state"] == "FAILED"
    assert result["error"] == "processing failed"


def test_normalize_task_status_running_clamps_progress() -> None:
    result = WebODMClient._normalize_task_status({"status": 20, "progress": 150})
    assert result == {"state": "RUNNING", "progress": 100}


def test_status_code_accepts_numeric_dict_payload() -> None:
    assert WebODMClient._status_code({"code": 20}) == 20


def test_nodeodm_options_payload_skips_none_values() -> None:
    payload = WebODMClient._nodeodm_options_payload({"dsm": True, "skip": None})
    assert '"name": "dsm"' in payload
    assert "skip" not in payload


def test_token_shape_helpers() -> None:
    assert WebODMClient._looks_like_jwt_token("header.payload.sig") is True
    assert WebODMClient._looks_like_uuid_token("12345678-1234-1234-1234-123456789abc") is True
    assert WebODMClient._looks_like_nodeodm_info({"version": "2.1", "taskQueueCount": 0}) is True


def test_is_retryable_http_exception_for_timeouts_and_503() -> None:
    assert WebODMClient._is_retryable_http_exception(httpx.TimeoutException("slow")) is True
    response = httpx.Response(503, request=httpx.Request("GET", "http://example"))
    assert WebODMClient._is_retryable_http_exception(
        httpx.HTTPStatusError("unavailable", request=response.request, response=response)
    ) is True

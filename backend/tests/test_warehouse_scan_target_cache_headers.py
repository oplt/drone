from fastapi import Response

from backend.modules.warehouse.routers.scan_targets import _set_scan_target_cache_headers


def test_scan_target_first_page_is_privately_cached() -> None:
    response = Response()

    _set_scan_target_cache_headers(response, offset=0)

    assert response.headers["Cache-Control"] == "private, max-age=10"
    assert response.headers["Vary"] == "Authorization"


def test_scan_target_later_pages_are_not_cached() -> None:
    response = Response()

    _set_scan_target_cache_headers(response, offset=200)

    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Vary"] == "Authorization"

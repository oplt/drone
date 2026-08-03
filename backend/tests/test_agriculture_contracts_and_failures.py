from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlparse
from datetime import UTC, datetime, timedelta

import pytest

from backend.modules.agriculture.contracts_validation import validate_geojson, validate_status_transition, validate_tile_bounds
from backend.modules.agriculture.storage import AgricultureStorage


def test_geojson_and_tile_contracts_reject_invalid_payloads():
    valid = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.3, 50.8]}, "properties": {}}
    assert validate_geojson(valid) is valid
    with pytest.raises(ValueError):
        validate_geojson({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]}})
    validate_tile_bounds(z=3, x=7, y=7)
    with pytest.raises(ValueError):
        validate_tile_bounds(z=3, x=8, y=0)


def test_status_contract_rejects_skipped_transitions():
    allowed = {"planned": {"preflight"}, "preflight": {"running"}}
    validate_status_transition("planned", "preflight", allowed)
    with pytest.raises(ValueError):
        validate_status_transition("planned", "running", allowed)


def test_storage_failure_matrix_covers_mismatch_expiry_and_outage_like_missing_object(tmp_path):
    storage = AgricultureStorage(tmp_path)
    key = "org/7/media/frame.jpg"
    data = b"not-a-jpeg"
    checksum = hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError, match="checksum"):
        storage.write_object(key, data, expected_checksum="0" * 64)
    storage.write_object(key, data, expected_checksum=checksum)
    with pytest.raises(ValueError, match="MIME"):
        storage.validate_file_content(key, declared_content_type="image/jpeg")
    signed = storage.sign(key, expires_in=30)
    assert "signature=" in signed
    with pytest.raises(ValueError, match="expired"):
        storage.verify(key, int((datetime.now(UTC) - timedelta(seconds=1)).timestamp()), "bad")
    query = parse_qs(urlparse(signed).query)
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.verify(key, int(query["expires"][0]), query["signature"][0])

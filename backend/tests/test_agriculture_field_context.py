import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from backend.modules.agriculture.field_context import _area_ha, _boundary_payload, _geometry, _owned


def polygon(*, self_intersecting: bool = False):
    coordinates = [[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]
    if self_intersecting:
        coordinates = [[0, 0], [0.01, 0.01], [0.01, 0], [0, 0.01], [0, 0]]
    return {"type": "Polygon", "coordinates": [coordinates]}


def test_valid_wgs84_polygon_supports_holes_and_area():
    payload = polygon()
    payload["coordinates"].append([[0.002, 0.002], [0.003, 0.002], [0.003, 0.003], [0.002, 0.002]])
    parsed = _geometry(payload, field_name="boundary")
    assert parsed.is_valid
    assert _area_ha(parsed) > 0
    assert _boundary_payload(payload)["type"] == "Polygon"


def test_self_intersection_is_rejected_with_field_error():
    with pytest.raises(HTTPException) as exc:
        _geometry(polygon(self_intersecting=True), field_name="boundary")
    assert exc.value.status_code == 422
    assert exc.value.detail["field"] == "boundary"
    assert exc.value.detail["code"] == "AGRICULTURE_GEOMETRY_INVALID"


def test_non_wgs84_crs_is_rejected():
    payload = polygon()
    payload["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(HTTPException) as exc:
        _geometry(payload, field_name="boundary")
    assert exc.value.detail["code"] == "AGRICULTURE_CRS_UNSUPPORTED"


@pytest.mark.asyncio
async def test_field_context_uses_ownership_guard(monkeypatch):
    async def no_access(*args, **kwargs):
        return None

    from backend.modules.agriculture import field_context
    monkeypatch.setattr(field_context.field_service, "get_owned", no_access)
    with pytest.raises(HTTPException) as exc:
        await _owned(99, SimpleNamespace(user=SimpleNamespace(id=1), org_id=7), SimpleNamespace())
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "FIELD_NOT_FOUND"

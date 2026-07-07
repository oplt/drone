from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

import pytest
from pydantic import ValidationError

from backend.core.geometry.coordinates import extract_lonlat_pairs
from backend.core.geometry.projection import (
    close_lonlat_ring,
    lonlat_to_xy_m,
    polygon_centroid_lonlat,
    strip_closed_ring,
    xy_m_to_lonlat,
)
from backend.core.geometry.rings import ensure_closed_ring
from backend.core.tokens import safe_token
from backend.entrypoints.workers.async_loop import WorkerLoopState
from backend.modules.alerts.recipient_parsing import parse_delimited_tokens
from backend.modules.missions.schemas.mission_create import (
    MissionCreateIn,
    PrivatePatrolMissionParams,
    validate_private_patrol_task_inputs,
)
from backend.modules.missions.schemas.mission_types import MissionType
from backend.modules.missions.service.mission_start import (
    ALLOW_WARN_PREFLIGHT_START,
    mission_fingerprint,
    preflight_allows_start,
)
from backend.modules.preflight.checks.async_invocation import call_maybe_async
from backend.modules.preflight.weather.coercion import to_float_or_none, to_int_or_none
from backend.modules.warehouse.service.runtime_settings import setting_float, setting_int
from backend.modules.warehouse.repository.contracts import WarehouseRepositoryError
from backend.modules.warehouse.repository.query_values import (
    clamp_list_limit,
    require_json_object,
)


def test_extract_lonlat_pairs_flattens_nested_numeric_coordinates() -> None:
    assert extract_lonlat_pairs([[[4, 50], [5.5, 51.5]], "ignored", [6, 52, 99]]) == [
        (4.0, 50.0),
        (5.5, 51.5),
        (6.0, 52.0),
    ]
    assert extract_lonlat_pairs(None) == []


def test_parse_delimited_tokens_preserves_order_and_removes_duplicates() -> None:
    assert parse_delimited_tokens(" a@example.com; b@example.com a@example.com ") == [
        "a@example.com",
        "b@example.com",
    ]
    assert parse_delimited_tokens("") == []


@pytest.mark.asyncio
async def test_call_maybe_async_supports_async_sync_and_awaitable_results() -> None:
    async def async_provider(value: int) -> int:
        return value + 1

    def sync_provider(value: int) -> int:
        return value + 2

    def awaitable_provider(value: int) -> Coroutine[Any, Any, int]:
        async def result() -> int:
            return value + 3

        return result()

    assert await call_maybe_async(async_provider, 1) == 2
    assert await call_maybe_async(sync_provider, 1) == 3
    assert await call_maybe_async(awaitable_provider, 1) == 4


def test_worker_loop_state_reuses_only_its_own_open_loop() -> None:
    first_state = WorkerLoopState()
    second_state = WorkerLoopState()
    first_loop = first_state.get_loop()
    try:
        assert first_state.get_loop() is first_loop
        assert second_state.get_loop() is not first_loop
    finally:
        first_loop.close()
        second_state.get_loop().close()


def test_warehouse_query_values_preserve_defaults_bounds_and_errors() -> None:
    assert clamp_list_limit("invalid", default=50) == 50  # type: ignore[arg-type]
    assert clamp_list_limit(0, default=100) == 1
    assert clamp_list_limit(999, default=100) == 500
    assert require_json_object(None, field_name="metadata") == {}
    original = {"key": "value"}
    assert require_json_object(original, field_name="metadata") == original
    assert require_json_object(original, field_name="metadata") is not original
    with pytest.raises(WarehouseRepositoryError, match="metadata must be a JSON object\\."):
        require_json_object([], field_name="metadata")  # type: ignore[arg-type]


def test_mission_preflight_decision_and_fingerprint_are_stable() -> None:
    assert preflight_allows_start("pass") is True
    assert preflight_allows_start("fail") is False
    assert preflight_allows_start("warn") is ALLOW_WARN_PREFLIGHT_START

    payload = MissionCreateIn(mission_type=MissionType.CONTROLLED, name="stable")
    assert mission_fingerprint(payload) == mission_fingerprint(payload.model_copy())


def test_shared_geometry_helpers_preserve_ring_and_projection_behavior() -> None:
    ring = [(4.0, 50.0), (5.0, 50.0), (5.0, 51.0)]
    assert close_lonlat_ring(ring) == [*ring, ring[0]]
    assert strip_closed_ring([*ring, ring[0]]) == ring
    assert ensure_closed_ring([[4.0, 50.0], [5.0, 50.0], [5.0, 51.0]]) == [
        [4.0, 50.0],
        [5.0, 50.0],
        [5.0, 51.0],
        [4.0, 50.0],
    ]
    assert polygon_centroid_lonlat([*ring, ring[0]]) == pytest.approx((14.0 / 3.0, 151.0 / 3.0))

    x, y = lonlat_to_xy_m(4.001, 50.002, 4.0, 50.0)
    lon, lat = xy_m_to_lonlat(x, y, 4.0, 50.0)
    assert lon == pytest.approx(4.001)
    assert lat == pytest.approx(50.002)


def test_weather_and_runtime_value_coercion_helpers_match_local_contracts() -> None:
    assert to_float_or_none("1.25") == 1.25
    assert to_float_or_none(None) is None
    assert to_float_or_none("bad") is None
    assert to_int_or_none("7") == 7
    assert to_int_or_none("bad") is None
    assert setting_float("bad", minimum=0.2, default=1.0) == 1.0
    assert setting_float("-1", minimum=0.2, default=1.0) == 0.2
    assert setting_int("bad", minimum=1, default=50) == 50
    assert setting_int("-5", minimum=1, default=50) == 1


def test_safe_token_shared_across_capture_paths() -> None:
    assert safe_token("../flight id!!") == "flight_id"
    assert safe_token("") == "unknown"


def test_private_patrol_validation_contract_is_shared() -> None:
    polygon = [[4.0, 50.0], [4.1, 50.0], [4.1, 50.1]]
    params = PrivatePatrolMissionParams(
        task_type="grid_surveillance",
        property_polygon_lonlat=polygon,
    )
    payload = MissionCreateIn(
        mission_type=MissionType.PRIVATE_PATROL,
        private_patrol=params,
    )
    assert payload.private_patrol is params

    with pytest.raises(ValueError, match="key_points_lonlat"):
        validate_private_patrol_task_inputs(
            task_type="waypoint_patrol",
            property_polygon_lonlat=None,
            key_points_lonlat=[[4.0, 50.0]],
        )
    with pytest.raises(ValidationError, match="property_polygon_lonlat geofence"):
        PrivatePatrolMissionParams(task_type="event_triggered_patrol")

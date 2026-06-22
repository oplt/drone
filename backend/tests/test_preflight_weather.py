from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

from backend.modules.preflight.checks.schemas import CheckStatus
from backend.modules.preflight.weather.evaluation import evaluate_weather_preflight
from backend.modules.preflight.weather.location import is_belgium_coordinates, is_outdoor_preflight_mission
from backend.modules.preflight.weather.models import WeatherSnapshot
from backend.modules.preflight.weather.thresholds import WeatherThresholds


def _thresholds(**overrides: object) -> WeatherThresholds:
    base = WeatherThresholds(
        enabled=True,
        fail_policy="warn",
        wind_max_mps=12.0,
        gust_max_mps=15.0,
        max_precip_mm=0.5,
        min_visibility_m=3000.0,
        max_cloud_cover_pct=90.0,
        min_temp_c=-10.0,
        max_temp_c=40.0,
        blocked_weather_codes=frozenset({45, 48, 65, 95, 96, 99}),
        warn_weather_codes=frozenset({51, 80}),
        kmi_validation_enabled=True,
        kmi_max_obs_age_hours=6.0,
        kmi_wind_delta_warn_mps=4.0,
        kmi_wind_delta_block_mps=8.0,
        open_meteo_base_url="https://api.open-meteo.com/v1/forecast",
        kmi_wfs_base_url="https://opendata.meteo.be/service/aws/ows",
        cache_ttl_s=300.0,
    )
    return WeatherThresholds(**{**base.__dict__, **overrides})


def _snapshot(**overrides: object) -> WeatherSnapshot:
    base = WeatherSnapshot(
        latitude=50.93,
        longitude=5.34,
        source="open-meteo",
        wind_speed_mps=3.0,
        wind_gust_mps=5.0,
        precipitation_mm=0.0,
        visibility_m=10000.0,
        weather_code=0,
        temperature_c=18.0,
        cloud_cover_pct=20.0,
        fetched_at=time.time(),
    )
    return WeatherSnapshot(**{**base.__dict__, **overrides})


def _check_statuses(results: list, name: str) -> str:
    for result in results:
        if result.name == name:
            return str(result.status)
    raise AssertionError(f"Missing check {name!r}")


def test_safe_weather_passes() -> None:
    results = evaluate_weather_preflight(_snapshot(), thresholds=_thresholds())
    assert _check_statuses(results, "Weather Availability") == CheckStatus.PASS
    assert _check_statuses(results, "Wind Speed") == CheckStatus.PASS


def test_unsafe_wind_blocks() -> None:
    results = evaluate_weather_preflight(
        _snapshot(wind_speed_mps=14.0, wind_gust_mps=20.0),
        thresholds=_thresholds(),
    )
    assert _check_statuses(results, "Wind Speed") == CheckStatus.FAIL
    assert _check_statuses(results, "Wind Gust") == CheckStatus.FAIL
    assert "Blocked" in (results[0].message or "")


def test_rain_blocks() -> None:
    results = evaluate_weather_preflight(
        _snapshot(precipitation_mm=2.5, weather_code=65),
        thresholds=_thresholds(),
    )
    assert _check_statuses(results, "Precipitation") == CheckStatus.FAIL


def test_low_visibility_blocks() -> None:
    results = evaluate_weather_preflight(
        _snapshot(visibility_m=800.0, weather_code=45),
        thresholds=_thresholds(),
    )
    assert _check_statuses(results, "Visibility") == CheckStatus.FAIL
    assert _check_statuses(results, "Weather Conditions") == CheckStatus.FAIL


def test_api_failure_warn_by_default() -> None:
    results = evaluate_weather_preflight(
        None,
        thresholds=_thresholds(fail_policy="warn"),
        api_error="timeout",
    )
    assert len(results) == 1
    assert results[0].status == CheckStatus.WARN
    assert "Warning" in (results[0].message or "")


def test_api_failure_block_policy() -> None:
    results = evaluate_weather_preflight(
        None,
        thresholds=_thresholds(fail_policy="block"),
        api_error="upstream unavailable",
    )
    assert results[0].status == CheckStatus.FAIL
    assert "Blocked" in (results[0].message or "")


def test_thunderstorm_code_blocks() -> None:
    results = evaluate_weather_preflight(
        _snapshot(weather_code=95),
        thresholds=_thresholds(),
    )
    assert _check_statuses(results, "Weather Conditions") == CheckStatus.FAIL


def test_kmi_validation_warn_on_delta() -> None:
    results = evaluate_weather_preflight(
        _snapshot(
            wind_speed_mps=4.0,
            kmi_wind_speed_mps=9.0,
            kmi_station_code=6477,
            kmi_station_name="UCCLE",
            kmi_observation_time="2026-06-21T12:00:00+00:00",
        ),
        thresholds=_thresholds(),
    )
    assert _check_statuses(results, "KMI/RMI Validation") == CheckStatus.WARN


def test_kmi_validation_skips_without_observation() -> None:
    results = evaluate_weather_preflight(_snapshot(), thresholds=_thresholds())
    assert _check_statuses(results, "KMI/RMI Validation") == CheckStatus.SKIP


def test_indoor_mission_types_skip_outdoor_weather() -> None:
    assert is_outdoor_preflight_mission("warehouse_scan") is False
    assert is_outdoor_preflight_mission("indoor_exploration") is False
    assert is_outdoor_preflight_mission("warehouse_inspection") is False
    assert is_outdoor_preflight_mission("private_patrol") is True
    assert is_outdoor_preflight_mission("grid") is True


def test_belgium_coordinate_detection() -> None:
    assert is_belgium_coordinates(50.93, 5.34) is True
    assert is_belgium_coordinates(48.85, 2.35) is False


def test_fetch_weather_uses_cache() -> None:
    import asyncio

    from backend.modules.preflight.weather import cache as weather_cache_mod
    from backend.modules.preflight.weather.service import fetch_weather_for_preflight

    async def _run() -> None:
        await weather_cache_mod._weather_cache.clear()
        sample = _snapshot()

        with patch(
            "backend.modules.preflight.weather.service.fetch_open_meteo_current",
            new=AsyncMock(return_value=sample),
        ) as mock_fetch:
            first, err1 = await fetch_weather_for_preflight(
                50.93, 5.34, config={"WEATHER_CACHE_TTL_S": 300}
            )
            second, err2 = await fetch_weather_for_preflight(
                50.93, 5.34, config={"WEATHER_CACHE_TTL_S": 300}
            )

        assert err1 is None and err2 is None
        assert first is not None and second is not None
        assert mock_fetch.await_count == 1

    asyncio.run(_run())


def test_fetch_skips_kmi_outside_belgium() -> None:
    import asyncio

    from backend.modules.preflight.weather.service import fetch_weather_for_preflight

    async def _run() -> None:
        sample = _snapshot(latitude=48.85, longitude=2.35)
        with (
            patch(
                "backend.modules.preflight.weather.service.fetch_open_meteo_current",
                new=AsyncMock(return_value=sample),
            ),
            patch(
                "backend.modules.preflight.weather.service.enrich_with_kmi_rmi_observation",
                new=AsyncMock(),
            ) as mock_kmi,
        ):
            snapshot, err = await fetch_weather_for_preflight(48.85, 2.35)

        assert err is None
        assert snapshot is not None
        mock_kmi.assert_not_called()

    asyncio.run(_run())


def test_kmi_fetch_requests_latest_sorted_observation() -> None:
    import asyncio
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    from backend.modules.preflight.weather.kmi_rmi import _fetch_latest_station_observation

    recent = (datetime.now(UTC) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "features": [
            {
                "properties": {
                    "timestamp": recent,
                    "wind_speed_10m": 3.1,
                    "wind_gusts_speed": 5.2,
                }
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_response)

    async def _run() -> None:
        with patch(
            "backend.modules.preflight.weather.kmi_rmi.httpx.AsyncClient",
            return_value=mock_client,
        ):
            obs = await _fetch_latest_station_observation(
                6477,
                wfs_base_url="http://wfs",
                timeout_s=5,
                max_obs_age_hours=6,
            )

        assert obs is not None
        assert obs["wind_speed_mps"] == 3.1
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["sortBy"] == "timestamp D"
        assert call_params["count"] == 1

    asyncio.run(_run())

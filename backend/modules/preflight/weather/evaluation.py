from __future__ import annotations

from backend.modules.preflight.checks.schemas import CheckResult, CheckStatus
from backend.modules.preflight.weather.models import WeatherSnapshot
from backend.modules.preflight.weather.thresholds import WeatherThresholds

_THUNDERSTORM_CODES = frozenset({95, 96, 99})


def evaluate_weather_preflight(
    snapshot: WeatherSnapshot | None,
    *,
    thresholds: WeatherThresholds,
    api_error: str | None = None,
) -> list[CheckResult]:
    """Evaluate outdoor weather safety. FAIL maps to user-facing BLOCK status."""
    if api_error or snapshot is None:
        message = api_error or "Weather data unavailable"
        policy = thresholds.fail_policy
        if policy == "block":
            return [
                CheckResult(
                    name="Weather Availability",
                    status=CheckStatus.FAIL,
                    message=f"Blocked: {message}",
                )
            ]
        if policy == "skip":
            return [
                CheckResult(
                    name="Weather Availability",
                    status=CheckStatus.SKIP,
                    message=message,
                )
            ]
        return [
            CheckResult(
                name="Weather Availability",
                status=CheckStatus.WARN,
                message=f"Warning: {message}",
            )
        ]

    results: list[CheckResult] = []
    results.extend(_check_wind(snapshot, thresholds))
    results.extend(_check_precipitation(snapshot, thresholds))
    results.extend(_check_visibility(snapshot, thresholds))
    results.extend(_check_weather_code(snapshot, thresholds))
    results.extend(_check_temperature(snapshot, thresholds))
    results.extend(_check_cloud_cover(snapshot, thresholds))
    results.extend(_check_kmi_validation(snapshot, thresholds))

    overall = _summarize_weather(results)
    results.insert(
        0,
        CheckResult(
            name="Weather Availability",
            status=overall,
            message=_overall_message(overall, results),
        ),
    )
    return results


def _summarize_weather(results: list[CheckResult]) -> CheckStatus:
    if any(r.status == CheckStatus.FAIL for r in results):
        return CheckStatus.FAIL
    if any(r.status == CheckStatus.WARN for r in results):
        return CheckStatus.WARN
    if results and all(r.status == CheckStatus.SKIP for r in results):
        return CheckStatus.SKIP
    return CheckStatus.PASS


def _overall_message(overall: CheckStatus, results: list[CheckResult]) -> str:
    if overall == CheckStatus.PASS:
        return "Outdoor weather within configured limits"
    blocked = [r for r in results if r.status == CheckStatus.FAIL]
    warned = [r for r in results if r.status == CheckStatus.WARN]
    if blocked:
        detail = blocked[0].message or blocked[0].name
        return f"Blocked: {detail}"
    if warned:
        detail = warned[0].message or warned[0].name
        return f"Warning: {detail}"
    return "Weather checks skipped"


def _check_wind(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    results: list[CheckResult] = []
    if snapshot.wind_speed_mps is None:
        results.append(
            CheckResult(name="Wind Speed", status=CheckStatus.SKIP, message="Wind speed not available")
        )
    elif snapshot.wind_speed_mps <= thresholds.wind_max_mps:
        results.append(
            CheckResult(
                name="Wind Speed",
                status=CheckStatus.PASS,
                message=f"{snapshot.wind_speed_mps:.1f} m/s",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Wind Speed",
                status=CheckStatus.FAIL,
                message=(
                    f"Blocked: wind speed {snapshot.wind_speed_mps:.1f} m/s "
                    f"> {thresholds.wind_max_mps:.1f} m/s"
                ),
            )
        )

    if snapshot.wind_gust_mps is None:
        results.append(
            CheckResult(name="Wind Gust", status=CheckStatus.SKIP, message="Wind gust not available")
        )
    elif snapshot.wind_gust_mps <= thresholds.gust_max_mps:
        results.append(
            CheckResult(
                name="Wind Gust",
                status=CheckStatus.PASS,
                message=f"{snapshot.wind_gust_mps:.1f} m/s",
            )
        )
    else:
        results.append(
            CheckResult(
                name="Wind Gust",
                status=CheckStatus.FAIL,
                message=(
                    f"Blocked: wind gusts {snapshot.wind_gust_mps:.1f} m/s "
                    f"> {thresholds.gust_max_mps:.1f} m/s"
                ),
            )
        )
    return results


def _check_precipitation(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    if snapshot.precipitation_mm is None:
        return [
            CheckResult(
                name="Precipitation",
                status=CheckStatus.SKIP,
                message="Precipitation not available",
            )
        ]
    if snapshot.precipitation_mm <= thresholds.max_precip_mm:
        return [
            CheckResult(
                name="Precipitation",
                status=CheckStatus.PASS,
                message=f"{snapshot.precipitation_mm:.1f} mm",
            )
        ]
    return [
        CheckResult(
            name="Precipitation",
            status=CheckStatus.FAIL,
            message=(
                f"Blocked: precipitation {snapshot.precipitation_mm:.1f} mm "
                f"> {thresholds.max_precip_mm:.1f} mm"
            ),
        )
    ]


def _check_visibility(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    if snapshot.visibility_m is None:
        return [
            CheckResult(
                name="Visibility",
                status=CheckStatus.SKIP,
                message="Visibility not available",
            )
        ]
    if snapshot.visibility_m >= thresholds.min_visibility_m:
        return [
            CheckResult(
                name="Visibility",
                status=CheckStatus.PASS,
                message=f"{snapshot.visibility_m:.0f} m",
            )
        ]
    return [
        CheckResult(
            name="Visibility",
            status=CheckStatus.FAIL,
            message=(
                f"Blocked: visibility {snapshot.visibility_m:.0f} m "
                f"< {thresholds.min_visibility_m:.0f} m"
            ),
        )
    ]


def _check_weather_code(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    code = snapshot.weather_code
    if code is None:
        return [
            CheckResult(
                name="Weather Conditions",
                status=CheckStatus.SKIP,
                message="Weather code not available",
            )
        ]
    if code in thresholds.blocked_weather_codes or code in _THUNDERSTORM_CODES:
        label = "thunderstorm" if code in _THUNDERSTORM_CODES else f"WMO code {code}"
        return [
            CheckResult(
                name="Weather Conditions",
                status=CheckStatus.FAIL,
                message=f"Blocked: adverse weather ({label})",
            )
        ]
    if code in thresholds.warn_weather_codes:
        return [
            CheckResult(
                name="Weather Conditions",
                status=CheckStatus.WARN,
                message=f"Warning: marginal weather (WMO code {code})",
            )
        ]
    return [
        CheckResult(
            name="Weather Conditions",
            status=CheckStatus.PASS,
            message=f"WMO code {code}",
        )
    ]


def _check_temperature(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    if snapshot.temperature_c is None:
        return [
            CheckResult(
                name="Temperature",
                status=CheckStatus.SKIP,
                message="Temperature not available",
            )
        ]
    temp = snapshot.temperature_c
    if temp < thresholds.min_temp_c:
        return [
            CheckResult(
                name="Temperature",
                status=CheckStatus.FAIL,
                message=f"Blocked: temperature {temp:.1f}°C < {thresholds.min_temp_c:.1f}°C",
            )
        ]
    if temp > thresholds.max_temp_c:
        return [
            CheckResult(
                name="Temperature",
                status=CheckStatus.FAIL,
                message=f"Blocked: temperature {temp:.1f}°C > {thresholds.max_temp_c:.1f}°C",
            )
        ]
    return [
        CheckResult(
            name="Temperature",
            status=CheckStatus.PASS,
            message=f"{temp:.1f}°C",
        )
    ]


def _check_cloud_cover(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    if snapshot.cloud_cover_pct is None:
        return [
            CheckResult(
                name="Cloud Cover",
                status=CheckStatus.SKIP,
                message="Cloud cover not available",
            )
        ]
    if snapshot.cloud_cover_pct <= thresholds.max_cloud_cover_pct:
        return [
            CheckResult(
                name="Cloud Cover",
                status=CheckStatus.PASS,
                message=f"{snapshot.cloud_cover_pct:.0f}%",
            )
        ]
    return [
        CheckResult(
            name="Cloud Cover",
            status=CheckStatus.WARN,
            message=(
                f"Warning: cloud cover {snapshot.cloud_cover_pct:.0f}% "
                f"> {thresholds.max_cloud_cover_pct:.0f}%"
            ),
        )
    ]


def _check_kmi_validation(snapshot: WeatherSnapshot, thresholds: WeatherThresholds) -> list[CheckResult]:
    if not thresholds.kmi_validation_enabled:
        return [
            CheckResult(
                name="KMI/RMI Validation",
                status=CheckStatus.SKIP,
                message="Belgium KMI/RMI validation disabled",
            )
        ]
    if snapshot.kmi_wind_speed_mps is None:
        return [
            CheckResult(
                name="KMI/RMI Validation",
                status=CheckStatus.SKIP,
                message="No recent KMI/RMI station observation available",
            )
        ]
    if snapshot.wind_speed_mps is None:
        return [
            CheckResult(
                name="KMI/RMI Validation",
                status=CheckStatus.SKIP,
                message="Open-Meteo wind unavailable for cross-check",
            )
        ]

    delta = abs(snapshot.kmi_wind_speed_mps - snapshot.wind_speed_mps)
    station = snapshot.kmi_station_name or f"code {snapshot.kmi_station_code}"
    obs_time = snapshot.kmi_observation_time or "unknown time"
    detail = (
        f"{station}: KMI {snapshot.kmi_wind_speed_mps:.1f} m/s vs forecast "
        f"{snapshot.wind_speed_mps:.1f} m/s (Δ {delta:.1f} m/s, obs {obs_time})"
    )
    if delta >= thresholds.kmi_wind_delta_block_mps:
        return [
            CheckResult(
                name="KMI/RMI Validation",
                status=CheckStatus.FAIL,
                message=f"Blocked: KMI/RMI disagrees with forecast — {detail}",
            )
        ]
    if delta >= thresholds.kmi_wind_delta_warn_mps:
        return [
            CheckResult(
                name="KMI/RMI Validation",
                status=CheckStatus.WARN,
                message=f"Warning: KMI/RMI differs from forecast — {detail}",
            )
        ]
    return [
        CheckResult(
            name="KMI/RMI Validation",
            status=CheckStatus.PASS,
            message=f"KMI/RMI consistent with forecast — {detail}",
        )
    ]

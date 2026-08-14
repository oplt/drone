"""Environmental and calibration gates for thermal agriculture products."""

from __future__ import annotations

from typing import Any


def build_environmental_context(
    supplied: dict[str, float] | None,
    sensor_status: dict[str, Any],
) -> dict[str, Any]:
    """Prefer explicit context, then fill gaps from fresh on-flight sensors."""
    context: dict[str, Any] = dict(supplied or {})
    sources = {key: "request" for key in context}
    weather = sensor_status.get("weather", {})
    if weather.get("status") == "pass":
        values = weather.get("values", {})
        for target, candidates in {
            "ambient_air_temp_c": (
                "ambient_air_temp_c",
                "air_temp_c",
                "temperature_c",
            ),
            "relative_humidity_pct": ("relative_humidity_pct", "humidity_pct"),
            "wind_speed_mps": ("wind_speed_mps",),
        }.items():
            value = next(
                (values.get(key) for key in candidates if values.get(key) is not None),
                None,
            )
            if target not in context and value is not None:
                context[target] = float(value)
                sources[target] = str(weather.get("reading_id") or "weather_sensor")

    humidity = sensor_status.get("humidity", {})
    humidity_value = (humidity.get("values") or {}).get("percent")
    if (
        humidity.get("status") == "pass"
        and "relative_humidity_pct" not in context
        and humidity_value is not None
    ):
        context["relative_humidity_pct"] = float(humidity_value)
        sources["relative_humidity_pct"] = str(humidity.get("reading_id") or "humidity_sensor")
    context["sources"] = sources
    return context


def thermal_calibration_ready(
    thermal_bands: list[Any],
    *,
    profile_calibration_ids: set[str],
    valid_calibrations: dict[str, Any],
) -> bool:
    """Require every thermal band to match a registered current calibration."""
    return bool(thermal_bands) and all(
        row.calibration_id
        and str(row.calibration_id) in profile_calibration_ids
        and row.alignment_status == "pass"
        and row.quality_status == "pass"
        and row.calibration_id in valid_calibrations
        and valid_calibrations[row.calibration_id].sensor_type == "thermal"
        and valid_calibrations[row.calibration_id].sensor_serial == row.sensor_serial
        for row in thermal_bands
    )

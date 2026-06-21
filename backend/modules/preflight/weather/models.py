from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WeatherSnapshot:
    """Normalized outdoor weather sample for preflight evaluation."""

    latitude: float
    longitude: float
    source: str
    wind_speed_mps: float | None = None
    wind_gust_mps: float | None = None
    precipitation_mm: float | None = None
    visibility_m: float | None = None
    weather_code: int | None = None
    temperature_c: float | None = None
    cloud_cover_pct: float | None = None
    fetched_at: float | None = None
    kmi_station_code: int | None = None
    kmi_station_name: str | None = None
    kmi_wind_speed_mps: float | None = None
    kmi_wind_gust_mps: float | None = None
    kmi_observation_time: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def wind_data_dict(self) -> dict[str, float]:
        data: dict[str, float] = {}
        if self.wind_speed_mps is not None:
            data["speed"] = float(self.wind_speed_mps)
        if self.wind_gust_mps is not None:
            data["gust"] = float(self.wind_gust_mps)
        return data

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "wind_speed_mps": self.wind_speed_mps,
            "wind_gust_mps": self.wind_gust_mps,
            "precipitation_mm": self.precipitation_mm,
            "visibility_m": self.visibility_m,
            "weather_code": self.weather_code,
            "temperature_c": self.temperature_c,
            "cloud_cover_pct": self.cloud_cover_pct,
            "fetched_at": self.fetched_at,
            "kmi_station_code": self.kmi_station_code,
            "kmi_station_name": self.kmi_station_name,
            "kmi_wind_speed_mps": self.kmi_wind_speed_mps,
            "kmi_wind_gust_mps": self.kmi_wind_gust_mps,
            "kmi_observation_time": self.kmi_observation_time,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeatherSnapshot:
        return cls(
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            source=str(data.get("source") or "unknown"),
            wind_speed_mps=_optional_float(data.get("wind_speed_mps")),
            wind_gust_mps=_optional_float(data.get("wind_gust_mps")),
            precipitation_mm=_optional_float(data.get("precipitation_mm")),
            visibility_m=_optional_float(data.get("visibility_m")),
            weather_code=_optional_int(data.get("weather_code")),
            temperature_c=_optional_float(data.get("temperature_c")),
            cloud_cover_pct=_optional_float(data.get("cloud_cover_pct")),
            fetched_at=_optional_float(data.get("fetched_at")),
            kmi_station_code=_optional_int(data.get("kmi_station_code")),
            kmi_station_name=data.get("kmi_station_name"),
            kmi_wind_speed_mps=_optional_float(data.get("kmi_wind_speed_mps")),
            kmi_wind_gust_mps=_optional_float(data.get("kmi_wind_gust_mps")),
            kmi_observation_time=data.get("kmi_observation_time"),
            errors=tuple(data.get("errors") or ()),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

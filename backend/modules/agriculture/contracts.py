"""Shared observation contract adapters for agriculture and irrigation outputs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MissionTelemetrySample:
    """Persistence-neutral telemetry used by georeferencing consumers."""

    timestamp_utc: datetime
    lat: float
    lon: float
    relative_altitude_m: float | None = None
    absolute_altitude_m: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    gps_quality: float | None = None
    id: int | str | None = None


def irrigation_observation_type(zone_type: str) -> str:
    value = zone_type.lower().replace("-", "_").replace(" ", "_")
    if any(token in value for token in ("water", "wet", "drain", "irrigat")):
        return "standing_water"
    return "agriculture_anomaly"


def irrigation_zone_to_observation(zone: Any) -> dict[str, Any]:
    """Map legacy irrigation anomaly zones without losing provenance."""
    geometry = zone.polygon_geojson or {
        "type": "Point",
        "coordinates": [float(zone.centroid_lon), float(zone.centroid_lat)],
    }
    metadata = zone.meta_data or {}
    return {
        "legacy_anomaly_zone_id": int(zone.id),
        "observation_type": irrigation_observation_type(str(zone.type)),
        "geometry_geojson": geometry,
        "georef_status": "resolved",
        "area_m2": zone.area_m2,
        "severity": max(0.0, min(1.0, float(zone.severity))),
        "confidence": max(0.0, min(1.0, float(zone.confidence))),
        "uncertainty": {"source": "irrigation_analytics", "metadata": metadata},
        "first_detected": None,
        "last_detected": None,
        "trend": "current",
        "evidence_ids": [str(value) for value in (zone.evidence_image_ids or [])],
        "sensor_values": {"source": "irrigation_analytics", "zone_type": str(zone.type)},
        "model_version": str(metadata.get("analytics_version", "irrigation-analytics")),
    }

"""Phase 5 stand, spacing, and weed-density run products."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.agriculture.models import (
    AgricultureAnalysisLayer,
    AgricultureAnalysisRun,
    AgricultureFlight,
)
from backend.modules.agriculture.stand import summarize_stands
from backend.modules.agriculture.weed_density import build_weed_density
from backend.modules.fields.models import Field


@dataclass(frozen=True, slots=True)
class Phase5RunProducts:
    stand_summary: dict[str, Any]
    weed_density: dict[str, Any]
    observation_payloads: list[dict[str, Any]]


def _stand_gap_payloads(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "observation_type": "stand_gap",
            "geometry_geojson": gap["geometry_geojson"],
            "georef_status": "resolved",
            "area_m2": gap["affected_area_m2"],
            "severity": gap["severity"],
            "confidence": gap["confidence"],
            "uncertainty": {
                "row_id": gap["row_id"],
                "gap_length_m": gap["gap_length_m"],
                "estimated_missing_plants": gap["estimated_missing_plants"],
                "assumptions": summary.get("assumptions", {}),
                "metric_distance_method": summary.get("metric_distance_method"),
            },
            "first_detected": None,
            "last_detected": None,
            "trend": "current",
            "evidence_ids": gap["evidence_ids"],
            "sensor_values": {
                "gap_length_m": gap["gap_length_m"],
                "affected_row": gap["row_id"],
                "estimated_missing_plants": gap["estimated_missing_plants"],
            },
            "model_version": "stand-gap-geometry.v1",
        }
        for gap in summary.get("gaps", [])
    ]


def _weed_hotspot_payloads(
    density: dict[str, Any], profile: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "observation_type": "weed_density_hotspot",
            "geometry_geojson": hotspot["geometry_geojson"],
            "georef_status": "resolved",
            "area_m2": hotspot["area_m2"],
            "severity": hotspot["severity"],
            "confidence": hotspot["confidence"],
            "uncertainty": {
                "density_method": "track_deduplicated_grid",
                "configuration": {
                    "cell_size_m": profile.get("weed_density_cell_m", 10.0),
                    "hotspot_percentile": profile.get("weed_hotspot_percentile", 0.8),
                },
            },
            "first_detected": None,
            "last_detected": None,
            "trend": "current",
            "evidence_ids": hotspot["evidence_ids"],
            "sensor_values": hotspot["sensor_values"],
            "model_version": "weed-density-grid.v1",
        }
        for hotspot in density.get("observations", [])
    ]


async def _previous_weed_density(
    db: AsyncSession,
    *,
    run: AgricultureAnalysisRun,
    flight: AgricultureFlight,
    profile: dict[str, Any],
) -> tuple[float | None, str | None]:
    if not run.baseline_flight_id:
        return None, None
    baseline_flight = await db.get(AgricultureFlight, run.baseline_flight_id)
    baseline_profile = baseline_flight.profile_snapshot if baseline_flight else {}
    comparable = bool(
        baseline_flight
        and baseline_flight.field_id == flight.field_id
        and (baseline_flight.quality_summary or {}).get("status") in {"pass", "warning"}
        and baseline_profile.get("crop_type") == profile.get("crop_type")
        and sorted(baseline_profile.get("sensor_inventory") or ["rgb"])
        == sorted(profile.get("sensor_inventory") or ["rgb"])
    )
    if not comparable:
        return None, None
    baseline_run = await db.scalar(
        select(AgricultureAnalysisRun)
        .where(
            AgricultureAnalysisRun.flight_id == run.baseline_flight_id,
            AgricultureAnalysisRun.status.in_(["completed", "review", "published"]),
        )
        .order_by(AgricultureAnalysisRun.created_at.desc())
        .limit(1)
    )
    if baseline_run is None:
        return None, None
    baseline_layer = await db.scalar(
        select(AgricultureAnalysisLayer).where(
            AgricultureAnalysisLayer.run_id == baseline_run.id,
            AgricultureAnalysisLayer.layer_name == "weed_density",
        )
    )
    value = (
        (baseline_layer.summary or {}).get("field_density_detections_per_m2")
        if baseline_layer
        else None
    )
    return (float(value), run.baseline_flight_id) if value is not None else (None, None)


class AgricultureAnalyticsService:
    async def analyze(
        self,
        db: AsyncSession,
        *,
        run: AgricultureAnalysisRun,
        flight: AgricultureFlight,
        profile: dict[str, Any],
        detections: list[Any],
    ) -> Phase5RunProducts:
        stand = summarize_stands(
            [
                row
                for row in detections
                if str(row.label).lower() in {"plant", "crop", "stand", "seedling"}
            ],
            row_spacing_m=profile.get("expected_row_spacing_m"),
            row_direction_deg=profile.get("row_direction_deg"),
            expected_plant_spacing_m=profile.get("expected_plant_spacing_m"),
            crop_type=profile.get("crop_type"),
            gap_multiplier=float(profile.get("stand_gap_multiplier") or 1.75),
        )
        field = await db.get(Field, flight.field_id)
        boundary = (
            mapping(to_shape(field.boundary))
            if field is not None and field.boundary is not None
            else None
        )
        previous_density, previous_flight_id = await _previous_weed_density(
            db, run=run, flight=flight, profile=profile
        )
        weeds = build_weed_density(
            [row for row in detections if "weed" in str(row.label).lower()],
            field_boundary_geojson=boundary,
            cell_size_m=float(profile.get("weed_density_cell_m") or 10.0),
            hotspot_percentile=float(profile.get("weed_hotspot_percentile") or 0.8),
            previous_density_per_m2=previous_density,
            previous_flight_id=previous_flight_id,
        )
        return Phase5RunProducts(
            stand_summary=stand,
            weed_density=weeds,
            observation_payloads=[
                *_stand_gap_payloads(stand),
                *_weed_hotspot_payloads(weeds, profile),
            ],
        )

    @staticmethod
    def persist_layers(
        db: AsyncSession,
        *,
        run_id: str,
        products: Phase5RunProducts,
        observations_by_type: dict[str, list[Any]],
    ) -> int:
        stand_rows = observations_by_type.get("stand_gap", [])
        stand_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": row.id,
                    "geometry": row.geometry_geojson,
                    "properties": {
                        "observation_id": row.id,
                        "severity": row.severity,
                        "confidence": row.confidence,
                        "area_m2": row.area_m2,
                        "affected_row": (row.sensor_values or {}).get("affected_row"),
                        "gap_length_m": (row.sensor_values or {}).get("gap_length_m"),
                        "estimated_missing_plants": (row.sensor_values or {}).get(
                            "estimated_missing_plants"
                        ),
                        "review_state": row.review_state,
                    },
                }
                for row in stand_rows
            ],
        }
        layers = [
            (
                "stand_gap",
                "ready" if products.stand_summary.get("gap_status") == "pass" else "blocked",
                stand_geojson,
                {
                    "count": len(stand_rows),
                    "area_m2": sum(row.area_m2 or 0 for row in stand_rows),
                    "gap_status": products.stand_summary.get("gap_status"),
                    "quality_warnings": products.stand_summary.get("quality_warnings", []),
                    "assumptions": products.stand_summary.get("assumptions", {}),
                },
            ),
            (
                "plant_spacing",
                (
                    "ready"
                    if (products.stand_summary.get("spacing") or {}).get("status") == "pass"
                    else "warning"
                ),
                {"type": "FeatureCollection", "features": []},
                {
                    **(products.stand_summary.get("spacing") or {}),
                    "rows": products.stand_summary.get("rows", []),
                    "metric_distance_method": products.stand_summary.get("metric_distance_method"),
                    "quality_warnings": products.stand_summary.get("quality_warnings", []),
                },
            ),
            (
                "weed_density",
                (
                    "ready"
                    if products.weed_density.get("status") == "pass"
                    else products.weed_density.get("status", "blocked")
                ),
                products.weed_density.get("geojson", {"type": "FeatureCollection", "features": []}),
                products.weed_density.get(
                    "summary", {"reason": products.weed_density.get("reason")}
                ),
            ),
        ]
        size = 0
        for name, status, geojson, summary in layers:
            encoded = json.dumps(geojson, sort_keys=True, separators=(",", ":"))
            size += len(encoded)
            db.add(
                AgricultureAnalysisLayer(
                    run_id=run_id,
                    layer_name=name,
                    status=status,
                    geojson=geojson,
                    summary=summary,
                    checksum=hashlib.sha256(encoded.encode()).hexdigest(),
                )
            )
        return size


agriculture_analytics_service = AgricultureAnalyticsService()

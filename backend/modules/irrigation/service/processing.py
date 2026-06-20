from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config.runtime import settings
from backend.modules.irrigation.domain.analytics import analyze_irrigation
from backend.modules.irrigation.domain.compositor import build_field_composite
from backend.modules.irrigation.models import (
    AnomalyZone,
    CaptureRecord,
    InspectionPoint,
    ProcessedFieldLayer,
)
from backend.modules.missions.runtime_models import MissionRuntime
from backend.modules.organizations.service import ownership_clause

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistedCapture:
    image_path: Path
    public_uri: str
    width: int | None
    height: int | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class IrrigationProcessingService:
    def __init__(self) -> None:
        self.storage_root = Path(settings.irrigation_storage_dir).resolve()
        self.capture_interval_s = max(0.25, settings.irrigation_capture_interval_s)
        self.fov_h_deg = settings.irrigation_camera_fov_h_deg
        self.fov_v_deg = settings.irrigation_camera_fov_v_deg
        self._mission_locks: dict[str, asyncio.Lock] = {}
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def mission_root(self, mission_id: str) -> Path:
        safe_mission_id = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in mission_id
        )
        return self.storage_root / safe_mission_id

    def mission_captures_dir(self, mission_id: str) -> Path:
        path = self.mission_root(mission_id) / "captures"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def mission_outputs_dir(self, mission_id: str) -> Path:
        path = self.mission_root(mission_id) / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def public_uri_for_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.storage_root)
        return f"/irrigation-assets/{relative.as_posix()}"

    def local_path_for_image_uri(self, image_uri: str) -> Path:
        if image_uri.startswith("/irrigation-assets/"):
            return self.storage_root / image_uri.removeprefix("/irrigation-assets/")
        return Path(image_uri)

    async def get_owned_mission(
        self,
        db: AsyncSession,
        *,
        mission_id: str,
        user,
    ) -> MissionRuntime | None:
        result = await db.execute(
            select(MissionRuntime)
            .where(MissionRuntime.client_flight_id == mission_id)
            .where(
                ownership_clause(
                    user=user,
                    owner_col=MissionRuntime.user_id,
                    org_col=MissionRuntime.org_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def persist_upload(
        self,
        *,
        mission_id: str,
        upload: UploadFile,
        timestamp_utc: datetime,
    ) -> PersistedCapture:
        extension = Path(upload.filename or "capture.jpg").suffix or ".jpg"
        filename = (
            f"{timestamp_utc.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}{extension.lower()}"
        )
        destination = self.mission_captures_dir(mission_id) / filename
        payload = await upload.read()
        destination.write_bytes(payload)
        image_array = np.frombuffer(payload, dtype=np.uint8)
        decoded = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        width = int(decoded.shape[1]) if decoded is not None else None
        height = int(decoded.shape[0]) if decoded is not None else None
        return PersistedCapture(
            image_path=destination,
            public_uri=self.public_uri_for_path(destination),
            width=width,
            height=height,
        )

    async def register_capture(
        self,
        db: AsyncSession,
        *,
        mission: MissionRuntime,
        image_uri: str,
        timestamp_utc: datetime,
        lat: float,
        lon: float,
        alt_m: float | None,
        yaw_deg: float | None,
        pitch_deg: float | None,
        roll_deg: float | None,
        waypoint_seq: int | None,
        frame_width: int | None,
        frame_height: int | None,
        meta_data: dict[str, Any] | None = None,
    ) -> CaptureRecord:
        capture = CaptureRecord(
            mission_id=mission.client_flight_id,
            org_id=mission.org_id,
            project_id=mission.project_id,
            image_uri=image_uri,
            timestamp_utc=timestamp_utc,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
            waypoint_seq=waypoint_seq,
            frame_width=frame_width,
            frame_height=frame_height,
            meta_data=meta_data or {},
        )
        db.add(capture)
        await db.flush()

        sidecar_path = self.mission_captures_dir(mission.client_flight_id) / f"{capture.id}.json"
        sidecar_path.write_text(
            json.dumps(
                {
                    "capture_id": capture.id,
                    "mission_id": mission.client_flight_id,
                    "timestamp_utc": timestamp_utc.isoformat(),
                    "lat": lat,
                    "lon": lon,
                    "alt_m": alt_m,
                    "yaw_deg": yaw_deg,
                    "pitch_deg": pitch_deg,
                    "roll_deg": roll_deg,
                    "waypoint_seq": waypoint_seq,
                    "image_uri": image_uri,
                    "meta_data": meta_data or {},
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        logger.info(
            "Irrigation capture persisted: mission_id=%s capture_id=%s lat=%.6f lon=%.6f image_uri=%s",
            mission.client_flight_id,
            capture.id,
            lat,
            lon,
            image_uri,
        )
        return capture

    async def list_captures(self, db: AsyncSession, *, mission_id: str) -> list[CaptureRecord]:
        result = await db.execute(
            select(CaptureRecord)
            .where(CaptureRecord.mission_id == mission_id)
            .order_by(CaptureRecord.timestamp_utc.asc())
        )
        return list(result.scalars().all())

    async def get_or_create_layer(
        self, db: AsyncSession, *, mission: MissionRuntime
    ) -> ProcessedFieldLayer:
        result = await db.execute(
            select(ProcessedFieldLayer).where(
                ProcessedFieldLayer.mission_id == mission.client_flight_id
            )
        )
        layer = result.scalar_one_or_none()
        if layer is None:
            layer = ProcessedFieldLayer(
                mission_id=mission.client_flight_id,
                org_id=mission.org_id,
                project_id=mission.project_id,
                status="pending",
            )
            db.add(layer)
            await db.flush()
        return layer

    async def process_mission(
        self,
        db: AsyncSession,
        *,
        mission: MissionRuntime,
        force: bool = False,
    ) -> ProcessedFieldLayer:
        mission_id = mission.client_flight_id
        lock = self._mission_locks.setdefault(mission_id, asyncio.Lock())
        async with lock:
            captures = await self.list_captures(db, mission_id=mission_id)
            layer = await self.get_or_create_layer(db, mission=mission)
            if layer.status == "completed" and not force:
                return layer
            if not captures:
                raise ValueError(f"No captures available for mission {mission_id}")

            layer.status = "running"
            layer.error = None
            layer.capture_count = len(captures)
            await db.flush()

            try:
                outputs_dir = self.mission_outputs_dir(mission_id)
                captures_for_composite = [
                    type(
                        "CompositeCapture",
                        (),
                        {
                            "id": capture.id,
                            "lat": capture.lat,
                            "lon": capture.lon,
                            "alt_m": capture.alt_m,
                            "image_uri": str(self.local_path_for_image_uri(capture.image_uri)),
                        },
                    )()
                    for capture in captures
                ]

                composite = await asyncio.to_thread(
                    build_field_composite,
                    captures=captures_for_composite,
                    output_dir=outputs_dir,
                    fov_h_deg=self.fov_h_deg,
                    fov_v_deg=self.fov_v_deg,
                )
                if not composite.footprints:
                    raise ValueError(
                        "No readable capture frames were available for composite generation."
                    )
                preview_public_uri = self.public_uri_for_path(composite.preview_path)
                bounds_payload = {
                    "min_lat": composite.bounds.min_lat,
                    "min_lon": composite.bounds.min_lon,
                    "max_lat": composite.bounds.max_lat,
                    "max_lon": composite.bounds.max_lon,
                    "origin_lat": float(sum(float(c.lat) for c in captures) / len(captures)),
                    "origin_lon": float(sum(float(c.lon) for c in captures) / len(captures)),
                    "min_x_m": min(
                        footprint.local_bounds_m[0] for footprint in composite.footprints
                    ),
                    "max_y_m": max(
                        footprint.local_bounds_m[3] for footprint in composite.footprints
                    ),
                }
                analysis = await asyncio.to_thread(
                    analyze_irrigation,
                    preview_path=composite.preview_path,
                    resolution_m_per_px=composite.resolution_m_per_px,
                    bounds=bounds_payload,
                    capture_ids=[int(capture.id) for capture in captures],
                )

                await db.execute(
                    delete(InspectionPoint).where(InspectionPoint.mission_id == mission_id)
                )
                await db.execute(delete(AnomalyZone).where(AnomalyZone.mission_id == mission_id))
                await db.flush()

                for zone_payload in analysis["zones"]:
                    db.add(
                        AnomalyZone(
                            mission_id=mission_id,
                            layer_id=layer.id,
                            org_id=mission.org_id,
                            project_id=mission.project_id,
                            type=zone_payload["type"],
                            severity=zone_payload["severity"],
                            confidence=zone_payload["confidence"],
                            area_m2=zone_payload["area_m2"],
                            centroid_lat=zone_payload["centroid_lat"],
                            centroid_lon=zone_payload["centroid_lon"],
                            polygon_geojson=zone_payload["polygon_geojson"],
                            evidence_image_ids=zone_payload["evidence_image_ids"],
                            meta_data=zone_payload["meta_data"],
                        )
                    )
                await db.flush()

                zones_result = await db.execute(
                    select(AnomalyZone)
                    .where(AnomalyZone.mission_id == mission_id)
                    .order_by(AnomalyZone.severity.desc(), AnomalyZone.id.asc())
                )
                persisted_zones = list(zones_result.scalars().all())
                for index, point_payload in enumerate(analysis["inspection_points"]):
                    matching_zone = persisted_zones[index] if index < len(persisted_zones) else None
                    db.add(
                        InspectionPoint(
                            mission_id=mission_id,
                            zone_id=matching_zone.id if matching_zone else None,
                            org_id=mission.org_id,
                            project_id=mission.project_id,
                            lat=point_payload["lat"],
                            lon=point_payload["lon"],
                            label=point_payload["label"],
                            priority=point_payload["priority"],
                            meta_data=point_payload["meta_data"],
                        )
                    )

                layer.status = "completed"
                layer.capture_count = len(captures)
                layer.stitched_image_uri = preview_public_uri
                layer.resolution_m_per_px = composite.resolution_m_per_px
                layer.footprints_geojson = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "capture_id": footprint.capture_id,
                                "image_uri": self.public_uri_for_path(
                                    self.local_path_for_image_uri(footprint.image_uri)
                                ),
                            },
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[lon, lat] for lat, lon in footprint.geo_polygon]],
                            },
                        }
                        for footprint in composite.footprints
                    ],
                }
                layer.bounds_geojson = {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [composite.bounds.min_lon, composite.bounds.min_lat],
                            [composite.bounds.max_lon, composite.bounds.min_lat],
                            [composite.bounds.max_lon, composite.bounds.max_lat],
                            [composite.bounds.min_lon, composite.bounds.max_lat],
                            [composite.bounds.min_lon, composite.bounds.min_lat],
                        ]
                    ],
                }
                layer.tile_manifest = {
                    "kind": "preview_overlay",
                    "image_uri": preview_public_uri,
                    "bounds": {
                        "north": composite.bounds.max_lat,
                        "south": composite.bounds.min_lat,
                        "east": composite.bounds.max_lon,
                        "west": composite.bounds.min_lon,
                    },
                    "preview_size_px": {
                        "width": composite.preview_width,
                        "height": composite.preview_height,
                    },
                }
                layer.summary = analysis["summary"]
                layer.completed_at = _utc_now()
                await db.commit()
                logger.info(
                    "Irrigation mission processed: mission_id=%s captures=%s anomalies=%s",
                    mission_id,
                    len(captures),
                    analysis["summary"]["total_anomaly_count"],
                )
                try:
                    from backend.modules.agents.hooks import schedule_agent_hook
                    from backend.modules.agents.schemas import AgentPhase, MissionAgentId

                    schedule_agent_hook(
                        AgentPhase.POSTFLIGHT,
                        agent_id=MissionAgentId.FIELD_SURVEY,
                        mission_type="grid",
                        client_flight_id=mission.client_flight_id,
                        mission_runtime_id=mission.id,
                        structured_payload={
                            "irrigation_trigger": True,
                            "irrigation_summary": analysis["summary"],
                            "mission_state": mission.state,
                        },
                    )
                except Exception:
                    logger.exception("Failed to schedule irrigation field survey agent")
                await db.refresh(layer)
                return layer
            except Exception as exc:
                await db.rollback()
                layer = await self.get_or_create_layer(db, mission=mission)
                layer.status = "failed"
                layer.error = str(exc)
                await db.commit()
                logger.exception("Irrigation mission processing failed: mission_id=%s", mission_id)
                raise


irrigation_service = IrrigationProcessingService()

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import WebSocket
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.modules.warehouse.service.frame_contract import ODOM_FRAME, WAREHOUSE_MAP_FRAME
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add

logger = logging.getLogger(__name__)
LIVE_MAP_FRAMES = {ODOM_FRAME, WAREHOUSE_MAP_FRAME}


def _canonical_live_frame(value: str) -> str:
    value = value.strip()
    if value not in LIVE_MAP_FRAMES:
        raise ValueError(f"live-map frame_id must be one of {sorted(LIVE_MAP_FRAMES)}")
    return value


def canonical_live_map_publish_frame(
    raw_frame: str | None,
    *,
    fallback: str = ODOM_FRAME,
) -> str:
    """Map ROS layer frames onto the live-map contract (odom / warehouse_map)."""
    cleaned = str(raw_frame or "").strip()
    if cleaned in LIVE_MAP_FRAMES:
        return cleaned
    fallback_clean = str(fallback or ODOM_FRAME).strip()
    if fallback_clean in LIVE_MAP_FRAMES:
        return fallback_clean
    return ODOM_FRAME


class WarehouseLivePose(BaseModel):
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    yaw_deg: float | None = None
    frame_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("frame_id")
    @classmethod
    def clean_frame_id(cls, value: str) -> str:
        return _canonical_live_frame(value)


LiveMapLayer = Literal[
    "mid360_lidar",
    "rgbd_colored",
    "rgbd_xyz_uncolored",
    "nvblox_color",
    "nvblox_esdf",
    "nvblox_tsdf",
    "nvblox_mesh",
]

LiveMapSource = Literal[
    "mid360_raw",
    "rgbd_colored",
    "rgbd_xyz_uncolored",
    "nvblox_color",
    "nvblox_esdf",
    "nvblox_tsdf",
    "nvblox_mesh",
    "odom",
]

NvbloxLiveStatus = Literal["off", "warming", "live", "degraded", "error"]


class WarehouseLiveVoxelChunk(BaseModel):
    id: str = Field(..., min_length=1, max_length=160)
    kind: Literal["mesh", "point_cloud", "occupancy", "esdf", "costmap"] = "mesh"
    url: str | None = None
    content_type: str | None = Field(default=None, max_length=120)
    asset_id: int | None = None
    block_ids: list[str] = Field(default_factory=list)
    point_count: int | None = Field(default=None, ge=0)
    byte_size: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    bbox_local_m: list[float] | None = Field(default=None, min_length=6, max_length=6)
    preview_points_m: list[list[float]] | None = Field(default=None, max_length=2000)
    sequence: int = Field(default=0, ge=0)
    source: LiveMapSource | None = None
    layer: LiveMapLayer | None = None
    layer_type: LiveMapLayer | None = None
    has_rgb: bool | None = None
    fields: list[str] = Field(default_factory=list)
    source_topic: str | None = Field(default=None, max_length=256)
    cloud_age_ms: float | None = Field(default=None, ge=0)
    transform_age_ms: float | None = Field(default=None, ge=0)
    encoding: str | None = Field(default=None, max_length=64)
    frame_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("frame_id")
    @classmethod
    def clean_frame_id(cls, value: str) -> str:
        return _canonical_live_frame(value)

    stamp: str | None = Field(default=None, max_length=64)
    priority: int | None = Field(default=None, ge=0, le=100)


class WarehouseLiveHealthFlags(BaseModel):
    coverage_percent: float | None = Field(default=None, ge=0, le=100)
    drift_estimate_m: float | None = Field(default=None, ge=0)
    stale_costmap: bool = False
    missing_mesh: bool = False
    missing_point_cloud: bool = False
    nvblox_ready: bool = False
    nvblox_status: NvbloxLiveStatus | None = None
    rgbd_live: bool | None = None
    lidar_live: bool | None = None
    mapping_recording: bool = False
    stack_running: bool = False


class WarehouseLiveProvisionalCandidate(BaseModel):
    entity_kind: Literal["aisle", "rack", "shelf", "bin", "zone", "inspection_target"] = (
        "inspection_target"
    )
    identity_key: str = Field(..., min_length=1, max_length=256)
    geometry: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0, le=1)
    state: Literal[
        "provisional",
        "needs_more_coverage",
        "needs_review",
        "ready_to_publish",
        "locked",
    ] = "provisional"
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    source_sequence: int | None = Field(default=None, ge=0)
    inspection_ready: bool = False

    @model_validator(mode="after")
    def never_live_inspection_ready(self) -> WarehouseLiveProvisionalCandidate:
        if self.inspection_ready:
            raise ValueError("live provisional candidates cannot be inspection-ready")
        if self.state == "locked":
            raise ValueError("live provisional candidates cannot be locked")
        return self


class WarehouseCoverageRepairHint(BaseModel):
    kind: Literal["extra_pass", "hover_rescan", "coverage_gap"] = "extra_pass"
    reason: str = Field(..., min_length=1, max_length=128)
    target_point: dict[str, float] = Field(default_factory=dict)
    pose_local_m: dict[str, float | str] | None = None
    bbox_local_m: list[float] | None = Field(default=None, min_length=6, max_length=6)
    source_candidate: str | None = Field(default=None, max_length=256)
    priority: int = Field(default=100, ge=0, le=100)


class WarehouseCoordinateLiveState(BaseModel):
    status: Literal[
        "provisional",
        "needs_more_coverage",
        "needs_review",
        "ready_to_publish",
        "locked",
    ] = "needs_more_coverage"
    inspection_ready: bool = False
    candidate_count: int = Field(default=0, ge=0)
    coverage_repair_count: int = Field(default=0, ge=0)
    message: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def live_state_not_inspection_ready(self) -> WarehouseCoordinateLiveState:
        if self.status != "locked" and self.inspection_ready:
            raise ValueError("provisional coordinate state cannot be inspection-ready")
        return self


class WarehouseLiveMapUpdate(BaseModel):
    type: Literal["live_map_update"] = "live_map_update"
    flight_id: str = Field(..., min_length=1, max_length=128)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    frame_id: str = Field(..., min_length=1, max_length=128)
    pose: WarehouseLivePose | None = None
    changed_chunks: list[WarehouseLiveVoxelChunk] = Field(default_factory=list)
    removed_chunk_ids: list[str] = Field(default_factory=list)
    scan_path_sample: list[WarehouseLivePose] = Field(default_factory=list)
    health: WarehouseLiveHealthFlags = Field(default_factory=WarehouseLiveHealthFlags)
    provisional_candidates: list[WarehouseLiveProvisionalCandidate] = Field(
        default_factory=list, max_length=200
    )
    coverage_repair_hints: list[WarehouseCoverageRepairHint] = Field(
        default_factory=list, max_length=200
    )
    coordinate_state: WarehouseCoordinateLiveState = Field(
        default_factory=WarehouseCoordinateLiveState
    )
    finalized_scan_job_id: int | None = None

    @field_validator("frame_id")
    @classmethod
    def clean_frame_id(cls, value: str) -> str:
        return _canonical_live_frame(value)

    @model_validator(mode="after")
    def consistent_frames(self) -> WarehouseLiveMapUpdate:
        nested = []
        if self.pose is not None:
            nested.append(("pose", self.pose.frame_id))
        nested.extend(
            (f"changed_chunks[{index}]", chunk.frame_id)
            for index, chunk in enumerate(self.changed_chunks)
        )
        nested.extend(
            (f"scan_path_sample[{index}]", pose.frame_id)
            for index, pose in enumerate(self.scan_path_sample)
        )
        mismatched = [name for name, frame_id in nested if frame_id != self.frame_id]
        if mismatched:
            logger.warning(
                "warehouse_live_map_frame_mismatch flight_id=%s frame_id=%s fields=%s",
                self.flight_id,
                self.frame_id,
                mismatched,
            )
            metric_add("warehouse_live_map_frame_mismatch_total", 1)
            try:
                from backend.modules.warehouse.observability.warehouse_coordinate_metrics import (
                    record_frame_mismatch,
                )

                record_frame_mismatch(layer="live_map_stream")
            except Exception:
                pass
            raise ValueError(
                f"live-map update frame_id={self.frame_id!r} conflicts with: {mismatched}"
            )
        return self


class WarehouseLiveMapManifestSummary(BaseModel):
    map_quality: str = "unknown"
    rgbd_colored_available: bool = False
    rgbd_cloud_available: bool = False
    rgbd_has_rgb: bool = False
    default_view_layer: str | None = None
    diagnostic_nvblox_layers: list[str] = Field(default_factory=list)
    nvblox_available: bool = False
    raw_lidar_only: bool = False
    chunk_counts: dict[str, int] = Field(default_factory=dict)
    point_counts: dict[str, int] = Field(default_factory=dict)
    missing_topics: list[str] = Field(default_factory=list)
    source_quality: dict[str, dict[str, Any]] = Field(default_factory=dict)
    chunk_quality: list[dict[str, Any]] = Field(default_factory=list)
    rack_face_coverage: dict[str, Any] = Field(default_factory=dict)
    coverage_repair: dict[str, Any] = Field(default_factory=dict)


class WarehouseLiveMapSnapshot(BaseModel):
    type: Literal["live_map_snapshot"] = "live_map_snapshot"
    flight_id: str
    status: Literal["empty", "live", "stale", "finalized"] = "empty"
    last_update_at: datetime | None = None
    updates: list[WarehouseLiveMapUpdate] = Field(default_factory=list)
    manifest: WarehouseLiveMapManifestSummary | None = None


class WarehouseLiveMapStream:
    def __init__(
        self,
        *,
        max_updates_per_flight: int = 1000,
        max_flights: int = 64,
        send_timeout_s: float = 5.0,
        max_concurrent_sends: int = 64,
        max_consecutive_send_timeouts: int = 4,
    ) -> None:
        self._updates: dict[str, deque[WarehouseLiveMapUpdate]] = {}
        self._clients: dict[str, set[WebSocket]] = {}
        self._finalized_jobs: dict[str, int] = {}
        self._max_updates_per_flight = max(1, int(max_updates_per_flight))
        self._max_flights = max(1, int(max_flights))
        self._send_timeout_s = max(0.1, float(send_timeout_s))
        self._send_semaphore = asyncio.Semaphore(max(1, int(max_concurrent_sends)))
        self._max_consecutive_send_timeouts = max(1, int(max_consecutive_send_timeouts))
        # Per-socket consecutive send-timeout counter. A slow client (busy
        # downloading chunks → TCP backpressure) must NOT be evicted on a single
        # timeout; that froze the live map mid-scan and only recovered on a
        # reconnect snapshot. We only drop it after several consecutive timeouts.
        self._send_timeout_strikes: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()

    async def _trim_flight_cache_locked(self) -> None:
        if len(self._updates) <= self._max_flights:
            return
        # Drop oldest non-client, non-finalized flight buffers first.
        protected = set(self._clients) | set(self._finalized_jobs)
        removable = [flight_id for flight_id in self._updates if flight_id not in protected]
        for flight_id in removable[: max(0, len(self._updates) - self._max_flights)]:
            self._updates.pop(flight_id, None)

    async def _send_update(
        self,
        client: WebSocket,
        payload: dict[str, Any],
    ) -> WebSocket | None:
        try:
            async with self._send_semaphore:
                with observed_span(
                    "api.websocket.publish",
                    flight_id=payload.get("flight_id"),
                    **{"websocket.message_type": str(payload.get("type") or "live_map_update")},
                ):
                    await asyncio.wait_for(
                        client.send_json(payload),
                        timeout=self._send_timeout_s,
                    )
            metric_add(
                "api_websocket_messages",
                attrs={"channel": "warehouse_live_map", "message_type": str(payload.get("type"))},
            )
            self._send_timeout_strikes.pop(client, None)
            return None
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            # Transient backpressure (client busy fetching chunks), not a
            # disconnect. Keep the client subscribed so it keeps receiving
            # chunk metadata live; only evict after repeated stalls.
            strikes = self._send_timeout_strikes.get(client, 0) + 1
            self._send_timeout_strikes[client] = strikes
            metric_add(
                "api_websocket_send_timeouts",
                attrs={"channel": "warehouse_live_map"},
            )
            if strikes >= self._max_consecutive_send_timeouts:
                self._send_timeout_strikes.pop(client, None)
                metric_add("api_websocket_disconnects", attrs={"channel": "warehouse_live_map"})
                return client
            return None
        except Exception:
            self._send_timeout_strikes.pop(client, None)
            metric_add("api_websocket_disconnects", attrs={"channel": "warehouse_live_map"})
            return client

    async def publish(self, update: WarehouseLiveMapUpdate) -> WarehouseLiveMapUpdate:
        async with self._lock:
            flight_updates = self._updates.setdefault(
                update.flight_id,
                deque(maxlen=self._max_updates_per_flight),
            )
            if flight_updates and flight_updates[-1].frame_id != update.frame_id:
                raise ValueError(
                    "live-map flight frame changed without an explicit transform: "
                    f"{flight_updates[-1].frame_id!r} -> {update.frame_id!r}"
                )
            flight_updates.append(update)
            if update.finalized_scan_job_id is not None:
                self._finalized_jobs[update.flight_id] = int(update.finalized_scan_job_id)
            await self._trim_flight_cache_locked()
            clients = tuple(self._clients.get(update.flight_id, set()))

        if not clients:
            return update

        payload = update.model_dump(mode="json")
        results = await asyncio.gather(
            *(self._send_update(client, payload) for client in clients),
            return_exceptions=True,
        )
        stale_clients = [
            item for item in results if item is not None and not isinstance(item, Exception)
        ]
        if stale_clients:
            async with self._lock:
                active = self._clients.get(update.flight_id)
                if active is not None:
                    active.difference_update(stale_clients)  # type: ignore[arg-type]
                    if not active:
                        self._clients.pop(update.flight_id, None)
        return update

    async def snapshot(
        self, flight_id: str, *, max_updates: int | None = None
    ) -> WarehouseLiveMapSnapshot:
        async with self._lock:
            all_updates = list(self._updates.get(flight_id, ()))
            finalized_job_id = self._finalized_jobs.get(flight_id)
        updates = all_updates[-max_updates:] if max_updates and max_updates > 0 else all_updates
        last_update = all_updates[-1].timestamp if all_updates else None
        status: Literal["empty", "live", "stale", "finalized"] = "empty"
        if finalized_job_id is not None:
            status = "finalized"
        elif last_update is not None:
            age_s = (datetime.now(UTC) - last_update).total_seconds()
            status = "stale" if age_s > 10 else "live"
        return WarehouseLiveMapSnapshot(
            flight_id=flight_id,
            status=status,
            last_update_at=last_update,
            updates=updates,
        )

    async def connect(self, flight_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.setdefault(flight_id, set()).add(websocket)
        try:
            snapshot = await self.snapshot(flight_id)
            with observed_span(
                "api.websocket.publish",
                flight_id=flight_id,
                **{"websocket.message_type": "live_map_snapshot"},
            ):
                await asyncio.wait_for(
                    websocket.send_json(snapshot.model_dump(mode="json")),
                    timeout=self._send_timeout_s,
                )
            metric_add(
                "api_websocket_messages",
                attrs={"channel": "warehouse_live_map", "message_type": "live_map_snapshot"},
            )
        except Exception:
            await self.disconnect(flight_id, websocket)
            raise

    async def disconnect(self, flight_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._clients.get(flight_id)
            if clients is None:
                return
            clients.discard(websocket)
            if not clients:
                self._clients.pop(flight_id, None)
            self._send_timeout_strikes.pop(websocket, None)
        metric_add("api_websocket_disconnects", attrs={"channel": "warehouse_live_map"})

    async def finalize(self, flight_id: str, job_id: int | None) -> None:
        if job_id is None:
            return
        async with self._lock:
            self._finalized_jobs[flight_id] = int(job_id)
            clients = tuple(self._clients.get(flight_id, set()))
        snapshot = await self.snapshot(flight_id)
        payload = {
            "type": "live_map_finalized",
            "flight_id": flight_id,
            "finalized_scan_job_id": int(job_id),
            "last_update_at": snapshot.last_update_at.isoformat()
            if snapshot.last_update_at
            else None,
        }
        results = await asyncio.gather(
            *(self._send_update(client, payload) for client in clients),
            return_exceptions=True,
        )
        stale_clients = [
            item for item in results if item is not None and not isinstance(item, Exception)
        ]
        if stale_clients:
            async with self._lock:
                active = self._clients.get(flight_id)
                if active is not None:
                    active.difference_update(stale_clients)  # type: ignore[arg-type]
                    if not active:
                        self._clients.pop(flight_id, None)

    async def clear(self, *, close_clients: bool = False) -> None:
        async with self._lock:
            clients = [client for values in self._clients.values() for client in values]
            self._updates.clear()
            self._clients.clear()
            self._finalized_jobs.clear()
        if close_clients:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)


warehouse_live_map_stream = WarehouseLiveMapStream()


def normalize_live_map_payload(payload: dict[str, Any]) -> WarehouseLiveMapUpdate:
    if "provisional_candidates" not in payload or "coverage_repair_hints" not in payload:
        try:
            from backend.modules.warehouse.service.provisional_mapping import (
                provisional_candidates_from_live_update,
            )

            candidates, repair_hints, coordinate_state = provisional_candidates_from_live_update(
                payload
            )
            payload = {
                **payload,
                "provisional_candidates": payload.get("provisional_candidates", candidates),
                "coverage_repair_hints": payload.get("coverage_repair_hints", repair_hints),
                "coordinate_state": payload.get("coordinate_state", coordinate_state),
            }
        except Exception:
            logger.debug("warehouse_live_provisional_candidates_failed", exc_info=True)
    return WarehouseLiveMapUpdate.model_validate(payload)

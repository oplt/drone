from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import WebSocket
from pydantic import BaseModel, Field

from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add


class WarehouseLivePose(BaseModel):
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    yaw_deg: float | None = None
    frame_id: str = "map"


LiveMapLayer = Literal[
    "mid360_lidar",
    "rgbd_colored",
    "nvblox_color",
    "nvblox_esdf",
    "nvblox_tsdf",
    "nvblox_mesh",
]

LiveMapSource = Literal[
    "mid360_raw",
    "rgbd_colored",
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
    encoding: str | None = Field(default=None, max_length=64)
    frame_id: str | None = Field(default=None, max_length=128)
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


class WarehouseLiveMapUpdate(BaseModel):
    type: Literal["live_map_update"] = "live_map_update"
    flight_id: str = Field(..., min_length=1, max_length=128)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    frame_id: str = Field(default="map", min_length=1, max_length=128)
    pose: WarehouseLivePose = Field(default_factory=WarehouseLivePose)
    changed_chunks: list[WarehouseLiveVoxelChunk] = Field(default_factory=list)
    removed_chunk_ids: list[str] = Field(default_factory=list)
    scan_path_sample: list[WarehouseLivePose] = Field(default_factory=list)
    health: WarehouseLiveHealthFlags = Field(default_factory=WarehouseLiveHealthFlags)
    finalized_scan_job_id: int | None = None


class WarehouseLiveMapManifestSummary(BaseModel):
    map_quality: str = "unknown"
    rgbd_colored_available: bool = False
    nvblox_available: bool = False
    raw_lidar_only: bool = False
    chunk_counts: dict[str, int] = Field(default_factory=dict)
    point_counts: dict[str, int] = Field(default_factory=dict)
    missing_topics: list[str] = Field(default_factory=list)


class WarehouseLiveMapSnapshot(BaseModel):
    type: Literal["live_map_snapshot"] = "live_map_snapshot"
    flight_id: str
    status: Literal["empty", "live", "stale", "finalized"] = "empty"
    last_update_at: datetime | None = None
    updates: list[WarehouseLiveMapUpdate] = Field(default_factory=list)
    manifest: WarehouseLiveMapManifestSummary | None = None


class WarehouseLiveMapStream:
    def __init__(self, *, max_updates_per_flight: int = 1000) -> None:
        self._updates: dict[str, deque[WarehouseLiveMapUpdate]] = {}
        self._clients: dict[str, set[WebSocket]] = {}
        self._finalized_jobs: dict[str, int] = {}
        self._max_updates_per_flight = max_updates_per_flight
        self._lock = asyncio.Lock()

    async def _send_update(
        self,
        client: WebSocket,
        payload: dict[str, Any],
    ) -> WebSocket | None:
        try:
            with observed_span(
                "api.websocket.publish",
                flight_id=payload.get("flight_id"),
                **{"websocket.message_type": str(payload.get("type") or "live_map_update")},
            ):
                await asyncio.wait_for(client.send_json(payload), timeout=1.0)
            metric_add(
                "api_websocket_messages",
                attrs={"channel": "warehouse_live_map", "message_type": str(payload.get("type"))},
            )
            return None
        except Exception:
            metric_add("api_websocket_disconnects", attrs={"channel": "warehouse_live_map"})
            return client

    async def publish(self, update: WarehouseLiveMapUpdate) -> WarehouseLiveMapUpdate:
        async with self._lock:
            flight_updates = self._updates.setdefault(
                update.flight_id,
                deque(maxlen=self._max_updates_per_flight),
            )
            flight_updates.append(update)
            if update.finalized_scan_job_id is not None:
                self._finalized_jobs[update.flight_id] = int(update.finalized_scan_job_id)
            clients = list(self._clients.get(update.flight_id, set()))

        payload = update.model_dump(mode="json")
        stale_clients = [
            stale
            for stale in await asyncio.gather(
                *(self._send_update(client, payload) for client in clients)
            )
            if stale is not None
        ]
        if stale_clients:
            async with self._lock:
                active = self._clients.get(update.flight_id)
                if active is not None:
                    active.difference_update(stale_clients)
        return update

    async def snapshot(self, flight_id: str) -> WarehouseLiveMapSnapshot:
        async with self._lock:
            updates = list(self._updates.get(flight_id, ()))
            finalized_job_id = self._finalized_jobs.get(flight_id)
        last_update = updates[-1].timestamp if updates else None
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
        snapshot = await self.snapshot(flight_id)
        with observed_span(
            "api.websocket.publish",
            flight_id=flight_id,
            **{"websocket.message_type": "live_map_snapshot"},
        ):
            await websocket.send_json(snapshot.model_dump(mode="json"))
        metric_add(
            "api_websocket_messages",
            attrs={"channel": "warehouse_live_map", "message_type": "live_map_snapshot"},
        )

    async def disconnect(self, flight_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._clients.get(flight_id)
            if clients is None:
                return
            clients.discard(websocket)
            if not clients:
                self._clients.pop(flight_id, None)
        metric_add("api_websocket_disconnects", attrs={"channel": "warehouse_live_map"})

    async def finalize(self, flight_id: str, job_id: int | None) -> None:
        if job_id is None:
            return
        async with self._lock:
            self._finalized_jobs[flight_id] = int(job_id)
        snapshot = await self.snapshot(flight_id)
        for client in list(self._clients.get(flight_id, set())):
            try:
                await client.send_json(
                    {
                        "type": "live_map_finalized",
                        "flight_id": flight_id,
                        "finalized_scan_job_id": int(job_id),
                        "last_update_at": snapshot.last_update_at.isoformat()
                        if snapshot.last_update_at
                        else None,
                    }
                )
            except Exception:
                await self.disconnect(flight_id, client)

    async def clear(self) -> None:
        async with self._lock:
            self._updates.clear()
            self._clients.clear()
            self._finalized_jobs.clear()


warehouse_live_map_stream = WarehouseLiveMapStream()


def normalize_live_map_payload(payload: dict[str, Any]) -> WarehouseLiveMapUpdate:
    return WarehouseLiveMapUpdate.model_validate(payload)

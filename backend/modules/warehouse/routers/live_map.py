from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, StreamingResponse

from backend.core.config.runtime import settings
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.missions.application import mission_application
from backend.modules.telemetry.websocket_api import _authenticate_websocket
from backend.modules.warehouse.service.live_map_storage import (
    LiveMapStorageError,
    StoredLiveMapChunk,
    warehouse_live_map_chunk_storage,
)
from backend.modules.warehouse.service.live_map_stream import (
    WarehouseLiveMapSnapshot,
    normalize_live_map_payload,
    warehouse_live_map_stream,
)
from backend.observability.instruments import observed_span
from backend.observability.metrics import add as metric_add
from backend.observability.metrics import record as metric_record

router = APIRouter(tags=["warehouse-live-map"])
logger = logging.getLogger(__name__)

WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS = 256
WAREHOUSE_LIVE_MAP_HTTP_SNAPSHOT_MAX_UPDATES = 5


class WarehouseLiveMapPublishOut(BaseModel):
    accepted: bool
    flight_id: str
    changed_chunk_count: int
    removed_chunk_count: int


class WarehouseLiveMapChunkUploadOut(BaseModel):
    accepted: bool
    flight_id: str
    chunk_id: str
    url: str
    byte_size: int
    checksum_sha256: str


class WarehouseLiveMapChunkBatchIn(BaseModel):
    chunk_ids: list[str] = Field(
        default_factory=list,
        max_length=WAREHOUSE_LIVE_MAP_BATCH_MAX_CHUNKS,
    )


def _live_map_ingest_authorized(ingest_key: str | None) -> bool:
    expected = str(getattr(settings, "warehouse_live_map_ingest_token", "") or "").strip()
    if not expected:
        logger.warning(
            "Warehouse live-map ingest token is not configured; rejecting ingest request"
        )
        return False
    return bool(ingest_key and hmac.compare_digest(str(ingest_key), expected))


@router.get("/live-map/config")
async def live_map_config(
    _org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    from backend.modules.warehouse.service.live_map_config import live_map_public_config

    return live_map_public_config()


@router.get("/live-map/diagnostics")
async def live_map_diagnostics(
    force: bool = Query(default=False),
    _org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    from backend.modules.warehouse.service.live_map_diagnostics import run_live_map_diagnostics

    report = await run_live_map_diagnostics(force=force)
    return report.as_dict()


@router.get("/live-map/{flight_id}/snapshot", response_model=WarehouseLiveMapSnapshot)
async def live_map_snapshot(
    flight_id: str,
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapSnapshot:
    started = time.monotonic()
    with observed_span("mapping.replay", flight_id=flight_id, map_id=flight_id):
        snapshot = await warehouse_live_map_stream.snapshot(
            flight_id,
            max_updates=WAREHOUSE_LIVE_MAP_HTTP_SNAPSHOT_MAX_UPDATES,
        )
    metric_record("mapping_replay_latency", (time.monotonic() - started) * 1000.0)
    try:
        from backend.observability.prometheus_metrics import (
            warehouse_mapping_replay_duration_seconds,
        )

        warehouse_mapping_replay_duration_seconds.observe(time.monotonic() - started)
    except Exception:
        logger.debug("Failed to record replay Prometheus metric", exc_info=True)
    return snapshot


@router.post("/live-map/{flight_id}/updates", response_model=WarehouseLiveMapPublishOut)
async def publish_live_map_update(
    flight_id: str,
    payload: dict[str, Any],
    x_warehouse_live_map_ingest_key: str | None = Header(
        None, alias="X-Warehouse-Live-Map-Ingest-Key"
    ),
) -> WarehouseLiveMapPublishOut:
    if not _live_map_ingest_authorized(x_warehouse_live_map_ingest_key):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-Warehouse-Live-Map-Ingest-Key",
        )
    with observed_span("mapping.live_update.publish", flight_id=flight_id, map_id=flight_id):
        update = normalize_live_map_payload({**payload, "flight_id": flight_id})
        await warehouse_live_map_stream.publish(update)
    metric_add("api_websocket_messages", attrs={"channel": "warehouse_live_map"})
    return WarehouseLiveMapPublishOut(
        accepted=True,
        flight_id=update.flight_id,
        changed_chunk_count=len(update.changed_chunks),
        removed_chunk_count=len(update.removed_chunk_ids),
    )


@router.post(
    "/live-map/{flight_id}/chunks/{chunk_id}",
    response_model=WarehouseLiveMapChunkUploadOut,
)
async def upload_live_map_chunk(
    flight_id: str,
    chunk_id: str,
    frame_id: Literal["odom", "warehouse_map"] = Query("odom"),
    kind: Literal["mesh", "point_cloud", "occupancy", "esdf", "costmap"] = Query("mesh"),
    sequence: int = Query(0, ge=0),
    bbox_local_m: list[float] | None = Query(default=None),
    point_count: int | None = Query(default=None, ge=0),
    file: UploadFile = File(...),
    _org_user: OrgUser = Depends(require_org_user),
) -> WarehouseLiveMapChunkUploadOut:
    if bbox_local_m is not None and len(bbox_local_m) != 6:
        raise HTTPException(status_code=422, detail="bbox_local_m must contain six values")
    try:
        started = time.monotonic()
        with observed_span(
            "mapping.save_chunk",
            flight_id=flight_id,
            map_id=flight_id,
            chunk_id=chunk_id,
            **{"mapping.layer": kind, "pointcloud.point_count": point_count},
        ):
            stored = await warehouse_live_map_chunk_storage.save_upload(
                flight_id=flight_id,
                chunk_id=chunk_id,
                frame_id=frame_id,
                kind=kind,
                upload=file,
            )
        metric_add("mapping_chunks_saved", attrs={"source": "api_upload", "layer": kind})
        metric_record(
            "mapping_chunk_save_latency",
            (time.monotonic() - started) * 1000.0,
            {"source": "api_upload", "layer": kind},
        )
    except LiveMapStorageError as exc:
        metric_add("mapping_chunk_save_failures", attrs={"source": "api_upload", "layer": kind})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    update = normalize_live_map_payload(
        {
            "flight_id": flight_id,
            "changed_chunks": [
                {
                    "id": stored.chunk_id,
                    "kind": kind,
                    "url": stored.url,
                    "content_type": stored.content_type,
                    "sequence": sequence,
                    "point_count": point_count,
                    "byte_size": stored.byte_size,
                    "checksum_sha256": stored.checksum_sha256,
                    "bbox_local_m": bbox_local_m,
                }
            ],
            "health": {
                "missing_mesh": kind != "mesh",
                "missing_point_cloud": kind != "point_cloud",
                "nvblox_ready": True,
                "mapping_recording": True,
                "stack_running": True,
            },
        }
    )
    await warehouse_live_map_stream.publish(update)
    metric_add("api_websocket_messages", attrs={"channel": "warehouse_live_map"})
    return WarehouseLiveMapChunkUploadOut(
        accepted=True,
        flight_id=flight_id,
        chunk_id=stored.chunk_id,
        url=stored.url,
        byte_size=stored.byte_size,
        checksum_sha256=stored.checksum_sha256,
    )


@router.get("/live-map/{flight_id}/chunks/{chunk_id}/download")
async def live_map_chunk_download(
    flight_id: str,
    chunk_id: str,
    request: Request,
    _org_user: OrgUser = Depends(require_org_user),
):
    with observed_span(
        "mapping.load_chunk",
        flight_id=flight_id,
        map_id=flight_id,
        chunk_id=chunk_id,
    ):
        stored = warehouse_live_map_chunk_storage.resolve(flight_id=flight_id, chunk_id=chunk_id)
    if stored is None:
        raise HTTPException(
            status_code=404,
            detail=f"Live map chunk {chunk_id!r} for flight {flight_id!r} was not found.",
        )
    etag = f'"{stored.checksum_sha256}"'
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "ETag": etag,
            },
        )
    return FileResponse(
        str(stored.path),
        media_type=stored.content_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/live-map/{flight_id}/chunks/-/batch")
async def live_map_chunk_batch_download(
    flight_id: str,
    payload: WarehouseLiveMapChunkBatchIn,
    _org_user: OrgUser = Depends(require_org_user),
):
    seen: set[str] = set()
    requested: list[str] = []
    for raw_id in payload.chunk_ids:
        chunk_id = str(raw_id)
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            requested.append(chunk_id)

    async def _resolve_chunk(
        chunk_id: str,
    ) -> tuple[str, StoredLiveMapChunk | None]:
        with observed_span(
            "mapping.load_chunk",
            flight_id=flight_id,
            map_id=flight_id,
            chunk_id=chunk_id,
        ):
            return chunk_id, await asyncio.to_thread(
                warehouse_live_map_chunk_storage.resolve,
                flight_id=flight_id,
                chunk_id=chunk_id,
            )

    def _frame_header(meta: dict[str, object]) -> bytes:
        body = json.dumps(meta, separators=(",", ":")).encode("utf-8")
        return len(body).to_bytes(4, "big") + body

    async def _stream():
        tasks = [asyncio.create_task(_resolve_chunk(chunk_id)) for chunk_id in requested]
        try:
            for completed in asyncio.as_completed(tasks):
                chunk_id, stored = await completed
                if stored is None:
                    yield _frame_header(
                        {
                            "chunk_id": chunk_id,
                            "status": 404,
                            "byte_size": 0,
                            "content_type": "application/octet-stream",
                            "checksum_sha256": "",
                        }
                    )
                    continue
                yield _frame_header(
                    {
                        "chunk_id": chunk_id,
                        "status": 200,
                        "byte_size": int(stored.byte_size),
                        "content_type": stored.content_type,
                        "checksum_sha256": stored.checksum_sha256,
                    }
                )
                data = await asyncio.to_thread(stored.path.read_bytes)
                yield data
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.websocket("/live-map/{flight_id}/stream")
async def websocket_live_map_stream(websocket: WebSocket, flight_id: str):
    user, auth_error = await _authenticate_websocket(websocket)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=auth_error)
        return

    runtime = await mission_application.get_by_client_id(flight_id)
    if runtime is None or runtime.org_id != user.org_id:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Live map flight is not available to this organization",
        )
        return

    with observed_span("api.websocket.connect", flight_id=flight_id):
        await warehouse_live_map_stream.connect(flight_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping" or '"type":"ping"' in message:
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await warehouse_live_map_stream.disconnect(flight_id, websocket)

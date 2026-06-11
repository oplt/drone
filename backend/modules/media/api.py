from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.infrastructure.camera.runtime import (
    drone_video_link_connected,
    shared_video_runtime,
)
from backend.modules.identity.dependencies import require_user, require_user_header_or_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["video"])

_DRONE_WAIT_RETRY_MS = 5000


def _drone_wait_detail() -> dict[str, Any]:
    return {
        "message": "Camera unavailable",
        "reason": "Drone is not connected",
        "source": shared_video_runtime.source_url(),
        "retry_after_ms": _DRONE_WAIT_RETRY_MS,
    }


@router.post("/start")
async def start_video_stream(user=Depends(require_user)):
    if not drone_video_link_connected():
        return {
            "status": "waiting_for_drone",
            "source": shared_video_runtime.source_url(),
            "proxy": "/video/mjpeg",
            "message": "Drone is not connected.",
            "retry_after_ms": _DRONE_WAIT_RETRY_MS,
        }

    current = await shared_video_runtime.readiness_status()
    retry_after_ms = int(current.get("retry_after_ms") or 0)
    if retry_after_ms > 0:
        return {
            "status": "unavailable",
            "source": current.get("source"),
            "proxy": "/video/mjpeg",
            "message": current.get("last_error") or current.get("error"),
            "retry_after_ms": retry_after_ms,
        }
    if current.get("state") == "warming":
        return {
            "status": "starting",
            "source": current.get("source"),
            "proxy": "/video/mjpeg",
            "message": "Video stream is starting.",
        }
    availability = await shared_video_runtime.ensure_source_available()
    if availability.get("status") == "skipped":
        return {
            "status": "skipped",
            "source": availability.get("source"),
            "proxy": "/video/mjpeg",
            "message": availability.get("message"),
        }
    try:
        status = await shared_video_runtime.ensure_running()
    except RuntimeError as exc:
        logger.warning(
            "Video stream unavailable source=%s status=%s error=%s",
            availability.get("source"),
            availability.get("status"),
            exc,
        )
        return {
            "status": "unavailable",
            "source": availability.get("source"),
            "proxy": "/video/mjpeg",
            "message": f"Video source is not accessible: {exc}",
        }
    return {
        "status": availability.get("status", "started"),
        "source": status.get("source"),
        "proxy": "/video/mjpeg",
        "message": availability.get("message"),
    }


@router.get("/status")
async def video_status(user=Depends(require_user_header_or_query)):
    return await shared_video_runtime.readiness_status()


@router.get("/mjpeg")
async def mjpeg_proxy(
    request: Request,
    user=Depends(require_user_header_or_query),
) -> StreamingResponse:
    if not drone_video_link_connected():
        raise HTTPException(
            status_code=503,
            detail=_drone_wait_detail(),
            headers={"Retry-After": str(_DRONE_WAIT_RETRY_MS // 1000)},
        )

    readiness = await shared_video_runtime.readiness_status()
    retry_after_ms = int(readiness.get("retry_after_ms") or 0)
    if retry_after_ms > 0:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Camera unavailable",
                "reason": readiness.get("last_error") or "Video stream in backoff",
                "source": readiness.get("source"),
                "retry_after_ms": retry_after_ms,
            },
            headers={"Retry-After": str(max(1, retry_after_ms // 1000))},
        )

    try:
        await shared_video_runtime.ensure_running()
    except RuntimeError as exc:
        readiness = await shared_video_runtime.readiness_status()
        retry_after_ms = int(readiness.get("retry_after_ms") or 0)
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Camera unavailable",
                "reason": str(exc),
                "source": readiness.get("source"),
                "retry_after_ms": retry_after_ms,
            },
            headers={"Retry-After": str(max(1, retry_after_ms // 1000))},
        ) from exc

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return StreamingResponse(
        shared_video_runtime.stream(request),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers=headers,
    )


@router.post("/recording/start")
async def start_recording(user=Depends(require_user)):
    return await shared_video_runtime.start_recording()


@router.post("/recording/stop")
async def stop_recording(user=Depends(require_user)):
    return await shared_video_runtime.stop_recording()


@router.get("/recording/status")
async def recording_status(user=Depends(require_user)):
    return await shared_video_runtime.status()

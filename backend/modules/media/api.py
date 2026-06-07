from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.infrastructure.camera.runtime import (
    shared_video_runtime,
)
from backend.modules.identity.dependencies import require_user, require_user_header_or_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["video"])


@router.post("/start")
async def start_video_stream(user=Depends(require_user)):
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


@router.get("/mjpeg")
async def mjpeg_proxy(
    request: Request,
    user=Depends(require_user_header_or_query),
) -> StreamingResponse:
    try:
        await shared_video_runtime.ensure_running()
    except RuntimeError as exc:
        status = await shared_video_runtime.status()
        logger.warning(
            "Video stream unavailable source=%s error=%s",
            status.get("source"),
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Camera unavailable",
                "reason": str(exc),
                "source": status.get("source"),
            },
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

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.auth.deps import require_user, require_user_header_or_query
from backend.video.runtime import (
    _ensure_gazebo_streaming_enabled,
    gazebo_gst_fallback_stream,
    gazebo_subprocess_fallback_required,
    shared_video_runtime,
)


router = APIRouter(prefix="/video", tags=["video"])


@router.post("/start")
async def start_video_stream(user=Depends(require_user)):
    availability = await shared_video_runtime.ensure_source_available()
    if gazebo_subprocess_fallback_required():
        return {
            "status": availability.get("status", "started"),
            "source": availability.get("source"),
            "proxy": "/video/mjpeg",
            "message": availability.get("message"),
        }

    status = await shared_video_runtime.ensure_running()
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
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    if gazebo_subprocess_fallback_required():
        await asyncio.to_thread(_ensure_gazebo_streaming_enabled)
        return StreamingResponse(
            gazebo_gst_fallback_stream(request),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers=headers,
        )
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

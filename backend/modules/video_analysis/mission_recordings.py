from __future__ import annotations

import logging
from pathlib import Path

from backend.core.database.session import Session
from backend.modules.missions.repository import mission_runtime_repo
from backend.modules.video_analysis.repository import VideoAnalysisRepository

logger = logging.getLogger(__name__)
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


async def register_mission_flight_recording(
    *,
    recording_path: str | None,
    recording_file: str | None,
    client_flight_id: str | None,
) -> None:
    """Link a finished mission MP4 to the video-analysis catalog."""
    if not client_flight_id:
        return

    path = _resolve_recording_path(recording_path, recording_file)
    if path is None:
        logger.info(
            "Skipping mission recording registration for %s: no recording file",
            client_flight_id,
        )
        return

    runtime = await mission_runtime_repo.get_by_client_id(client_flight_id)
    org_id = int(runtime.org_id) if runtime is not None and runtime.org_id is not None else None
    user_id = int(runtime.user_id) if runtime is not None and runtime.user_id is not None else None
    field_id = _field_id_from_runtime(runtime)

    try:
        async with Session() as db:
            repo = VideoAnalysisRepository(db)
            existing = await repo.get_video_by_storage_path(str(path))
            if existing is not None:
                if existing.mission_id in {None, client_flight_id}:
                    await repo.attach_video_to_mission(
                        existing,
                        mission_id=client_flight_id,
                        field_id=field_id or existing.field_id,
                    )
                return

            await repo.create_video(
                original_filename=path.name,
                storage_path=str(path),
                content_type="video/mp4",
                mission_id=client_flight_id,
                field_id=field_id,
                org_id=org_id,
                uploaded_by_user_id=user_id,
                status="mission_recording",
            )
            logger.info(
                "Registered mission recording mission_id=%s path=%s",
                client_flight_id,
                path,
            )
    except Exception:
        logger.exception(
            "Failed to register mission recording mission_id=%s path=%s",
            client_flight_id,
            path,
        )


def _resolve_recording_path(
    recording_path: str | None,
    recording_file: str | None,
) -> Path | None:
    if recording_path:
        candidate = Path(recording_path)
        if candidate.is_file() and candidate.suffix.lower() in VIDEO_SUFFIXES:
            return candidate.resolve()

    if recording_file:
        from backend.core.config.runtime import settings

        root = Path(settings.drone_video_save_path).resolve()
        candidate = root / recording_file
        if candidate.is_file():
            return candidate.resolve()

    return None


def _field_id_from_runtime(runtime) -> int | None:
    if runtime is None:
        return None
    params = getattr(runtime, "mission_params", None) or {}
    for key in ("field_id", "selected_field_id"):
        raw = params.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.modules.mapping.service.flight_capture import (
    IMAGE_EXTENSIONS,
    FlightCaptureSession,
    FlightCaptureSessionService,
)


class WarehouseCaptureSessionService(FlightCaptureSessionService):
    """Warehouse-flavoured capture session service.

    The photogrammetry service already implements the local sync/session
    mechanics this flow needs.  This subclass only switches the environment
    names and exposes warehouse method aliases used by scan.py.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sync_root = Path(
            os.getenv("WAREHOUSE_DRONE_SYNC_DIR", "backend/storage/warehouse_captures")
        ).resolve()
        staging_raw = os.getenv("WAREHOUSE_DRONE_CAPTURE_STAGING_DIR", "").strip()
        self.capture_staging_dir = Path(staging_raw).resolve() if staging_raw else None
        self.default_wait_timeout_s = float(os.getenv("WAREHOUSE_CAPTURE_SYNC_TIMEOUT_S", "120"))
        self.default_poll_interval_s = float(os.getenv("WAREHOUSE_CAPTURE_SYNC_POLL_S", "2"))
        self.default_min_images = max(0, int(os.getenv("WAREHOUSE_CAPTURE_SYNC_MIN_FILES", "1")))
        self.capture_sync_cmd_template = os.getenv("WAREHOUSE_CAPTURE_SYNC_CMD", "").strip()
        self.capture_sync_timeout_s = float(
            os.getenv("WAREHOUSE_CAPTURE_SYNC_CMD_TIMEOUT_S", "180")
        )
        self.sync_root.mkdir(parents=True, exist_ok=True)
        if self.capture_staging_dir:
            self.capture_staging_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _list_files(root: Path) -> list[Path]:
        if not root.exists():
            return []
        return sorted(p for p in root.rglob("*") if p.is_file())

    def import_external_files(
        self,
        session: FlightCaptureSession,
        *,
        capture_paths: list[str] | None,
    ) -> int:
        copied = 0
        for raw in capture_paths or []:
            src = Path(str(raw)).expanduser().resolve()
            if not src.exists() or not src.is_file():
                continue
            try:
                self._copy_into_session(session.session_dir, src)
                copied += 1
            except Exception:
                continue
        return copied

    def wait_for_files(
        self,
        session: FlightCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
    ) -> list[Path]:
        return self.wait_for_images(
            session,
            min_images=min_files,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )

    def finalize_session(
        self,
        session: FlightCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        files = self.wait_for_files(
            session,
            min_files=min_files,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        result = super().finalize_session(
            session,
            min_images=0,
            timeout_s=0,
            poll_interval_s=poll_interval_s,
            extra_meta=extra_meta,
        )
        all_files = self._list_files(session.session_dir)
        image_count = sum(1 for p in all_files if p.suffix.lower() in IMAGE_EXTENSIONS)
        result.update(
            {
                "file_count": len(all_files),
                "image_count": image_count,
                "files": [str(p) for p in all_files],
                "status": "ready" if len(files) >= max(0, int(min_files or 0)) else "incomplete",
            }
        )
        return result

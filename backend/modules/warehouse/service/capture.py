from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.modules.mapping.service.flight_capture import (
    IMAGE_EXTENSIONS,
    FlightCaptureSession,
    FlightCaptureSessionService,
)

logger = logging.getLogger(__name__)


class WarehouseCaptureSessionService(FlightCaptureSessionService):
    """Warehouse-flavoured capture session service.

    Reuses the common session primitives, but keeps warehouse logging,
    settings, and sync semantics separate from outdoor photogrammetry.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sync_root = Path(settings.warehouse_drone_sync_dir).resolve()
        staging_raw = settings.warehouse_drone_capture_staging_dir.strip()
        self.capture_staging_dir = Path(staging_raw).resolve() if staging_raw else None
        self.default_wait_timeout_s = settings.warehouse_capture_sync_timeout_s
        self.default_poll_interval_s = settings.warehouse_capture_sync_poll_s
        self.default_min_images = max(0, settings.warehouse_capture_sync_min_files)
        self.capture_sync_cmd_template = settings.warehouse_capture_sync_cmd.strip()
        self.capture_sync_timeout_s = settings.warehouse_capture_sync_cmd_timeout_s
        self.sync_root.mkdir(parents=True, exist_ok=True)
        if self.capture_staging_dir:
            self.capture_staging_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.isoformat()

    def start_session(self, *, flight_id: Any) -> FlightCaptureSession:
        safe_flight_id = self._sanitize_flight_id(flight_id)
        relative_dir = f"flight_{safe_flight_id}"
        session_dir = (self.sync_root / relative_dir).resolve()
        if not str(session_dir).startswith(str(self.sync_root)):
            raise RuntimeError("Resolved warehouse capture directory is outside sync root.")
        session_dir.mkdir(parents=True, exist_ok=True)

        session = FlightCaptureSession(
            flight_id=safe_flight_id,
            relative_source_dir=relative_dir,
            session_dir=session_dir,
            started_at=datetime.now(UTC),
        )
        self._write_manifest(
            session,
            {
                "flight_id": session.flight_id,
                "source_dir": session.relative_source_dir,
                "status": "started",
                "started_at": self._iso(session.started_at),
                "file_count": 0,
                "image_count": 0,
            },
        )
        logger.info(
            "Warehouse capture session prepared: flight_id=%s session_dir=%s",
            session.flight_id,
            session.session_dir,
        )
        return session

    @staticmethod
    def _list_files(root: Path) -> list[Path]:
        if not root.exists():
            return []
        return sorted(p for p in root.rglob("*") if p.is_file())

    def _import_from_staging(self, session: FlightCaptureSession) -> int:
        staging_dir = self.capture_staging_dir
        if staging_dir is None:
            return 0
        if not staging_dir.exists() or not staging_dir.is_dir():
            logger.warning(
                "WAREHOUSE_DRONE_CAPTURE_STAGING_DIR=%s is unavailable; staging import disabled.",
                staging_dir,
            )
            return 0
        start_ts = session.started_at.timestamp() - 1.0
        copied = 0
        for src in self._list_files(staging_dir):
            try:
                if src.stat().st_mtime < start_ts:
                    continue
                self._copy_into_session(session.session_dir, src)
                copied += 1
            except Exception:
                continue
        return copied

    def trigger_external_sync(
        self,
        session: FlightCaptureSession,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        if not self.capture_sync_cmd_template:
            return {
                "configured": False,
                "executed": False,
                "ok": False,
                "reason": "WAREHOUSE_CAPTURE_SYNC_CMD is not set",
            }
        result = super().trigger_external_sync(session, force=force)
        if result.get("configured"):
            logger.info(
                "Warehouse capture sync trigger: executed=%s ok=%s reason=%s",
                result.get("executed"),
                result.get("ok"),
                result.get("reason"),
            )
        return result

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
        needed = self.default_min_images if min_files is None else max(0, int(min_files))
        timeout = self.default_wait_timeout_s if timeout_s is None else max(0.0, float(timeout_s))
        poll = (
            self.default_poll_interval_s
            if poll_interval_s is None
            else max(0.2, float(poll_interval_s))
        )
        sync_state = self.trigger_external_sync(session)
        has_external_source = bool(sync_state.get("configured") or self.capture_staging_dir)
        imported = self._import_from_staging(session)
        files = self._list_files(session.session_dir)
        logger.info(
            "Warehouse capture file check: have=%s need=%s imported=%s timeout_s=%s",
            len(files),
            needed,
            imported,
            timeout if has_external_source else 0.0,
        )
        if needed <= 0 or len(files) >= needed or not has_external_source:
            return files

        deadline = time.monotonic() + timeout
        last_count = len(files)
        while time.monotonic() < deadline:
            time.sleep(poll)
            self._import_from_staging(session)
            files = self._list_files(session.session_dir)
            if len(files) != last_count:
                logger.info(
                    "Warehouse capture wait progress: %s/%s files in %s",
                    len(files),
                    needed,
                    session.session_dir,
                )
                last_count = len(files)
            if len(files) >= needed:
                break
        if needed > 0 and len(files) < needed:
            logger.warning(
                "Warehouse capture sync timeout: found %d/%d files in %s.",
                len(files),
                needed,
                session.session_dir,
            )
        return files

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
        ended_at = datetime.now(UTC)
        all_files = self._list_files(session.session_dir)
        image_count = sum(1 for p in all_files if p.suffix.lower() in IMAGE_EXTENSIONS)
        result: dict[str, Any] = {
            "flight_id": session.flight_id,
            "source_dir": session.relative_source_dir,
            "absolute_dir": str(session.session_dir),
            "started_at": self._iso(session.started_at),
            "ended_at": self._iso(ended_at),
            "file_count": len(all_files),
            "image_count": image_count,
            "files": [str(p) for p in all_files],
            "status": "ready" if len(files) >= max(0, int(min_files or 0)) else "incomplete",
            "min_files_expected": max(0, int(min_files or 0)),
        }
        if extra_meta:
            result["meta"] = dict(extra_meta)
        self._write_manifest(session, result)
        logger.info(
            "Warehouse capture session finalized: flight_id=%s status=%s file_count=%s manifest=%s",
            session.flight_id,
            result.get("status"),
            result.get("file_count"),
            self._manifest_path(session),
        )
        return result

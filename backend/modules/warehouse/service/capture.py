from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.core.config.runtime import settings
from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.mapping.service.flight_capture import (
    IMAGE_EXTENSIONS,
    FlightCaptureSession,
    FlightCaptureSessionService,
)
from backend.modules.warehouse.service.runtime_settings import (
    setting_float,
    setting_int,
    setting_text,
)

logger = logging.getLogger(__name__)


def _safe_float(value: object, *, minimum: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


class WarehouseCaptureSessionService(FlightCaptureSessionService):
    """Warehouse-flavoured capture session service.

    Reuses the common session primitives, but keeps warehouse logging,
    settings, and sync semantics separate from outdoor photogrammetry.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sync_root = Path(setting_text("warehouse_drone_sync_dir")).expanduser().resolve()

        staging_raw = setting_text("warehouse_drone_capture_staging_dir")
        self.capture_staging_dir = (
            Path(staging_raw).expanduser().resolve() if staging_raw else None
        )

        self.default_wait_timeout_s = setting_float(
            getattr(settings, "warehouse_capture_sync_timeout_s", 0.0),
            minimum=0.0,
            default=0.0,
        )
        self.default_poll_interval_s = setting_float(
            getattr(settings, "warehouse_capture_sync_poll_s", 1.0),
            minimum=0.2,
            default=1.0,
        )
        self.default_min_images = setting_int(
            getattr(settings, "warehouse_capture_sync_min_files", 0),
            minimum=0,
            default=0,
        )
        self.capture_sync_cmd_template = setting_text("warehouse_capture_sync_cmd")
        self.capture_sync_timeout_s = setting_float(
            getattr(settings, "warehouse_capture_sync_cmd_timeout_s", 0.0),
            minimum=0.0,
            default=0.0,
        )

        # Track files imported from the staging directory per session to avoid
        # repeatedly copying the same file on every polling iteration.
        self._staging_imported_by_session: dict[Path, set[Path]] = {}

        self.sync_root.mkdir(parents=True, exist_ok=True)
        if self.capture_staging_dir:
            self.capture_staging_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.isoformat()

    def _expected_min_files(self, min_files: int | None) -> int:
        return self.default_min_images if min_files is None else setting_int(min_files)

    def start_session(self, *, flight_id: Any) -> FlightCaptureSession:
        safe_flight_id = self._sanitize_flight_id(flight_id)
        relative_dir = f"flight_{safe_flight_id}"
        session_dir = (self.sync_root / relative_dir).resolve()

        if not _is_relative_to(session_dir, self.sync_root):
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
    def _iter_files(root: Path) -> Iterable[Path]:
        if not root.exists():
            return ()
        return (p for p in root.rglob("*") if p.is_file())

    @classmethod
    def _list_files(cls, root: Path) -> list[Path]:
        return sorted(cls._iter_files(root))

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

        session_key = session.session_dir.resolve()
        already_imported = self._staging_imported_by_session.setdefault(session_key, set())
        start_ts = session.started_at.timestamp() - 1.0
        copied = 0

        for src in self._list_files(staging_dir):
            try:
                src = src.resolve()
                if src in already_imported:
                    continue

                src_stat = src.stat()
                if src_stat.st_mtime < start_ts:
                    continue

                self._copy_into_session(session.session_dir, src)
                already_imported.add(src)
                copied += 1
            except OSError:
                logger.exception("Failed to stat/import staged capture file: %s", src)
            except Exception:
                logger.exception("Failed to copy staged capture file into session: %s", src)

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
            try:
                src = Path(str(raw)).expanduser().resolve()
                if not src.exists() or not src.is_file():
                    logger.debug("Skipping missing/non-file external capture path: %s", raw)
                    continue

                self._copy_into_session(session.session_dir, src)
                copied += 1
            except OSError:
                logger.exception("Failed to access external capture path: %s", raw)
            except Exception:
                logger.exception("Failed to import external capture path: %s", raw)
        return copied

    async def import_external_files_async(
        self,
        session: FlightCaptureSession,
        *,
        capture_paths: list[str] | None,
    ) -> int:
        return await run_blocking(
            self.import_external_files,
            session,
            capture_paths=capture_paths,
            boundary="filesystem",
            operation="warehouse_capture_import",
            timeout_s=60.0,
        )

    def wait_for_files(
        self,
        session: FlightCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
    ) -> list[Path]:
        needed = self._expected_min_files(min_files)
        timeout = (
            self.default_wait_timeout_s
            if timeout_s is None
            else _safe_float(timeout_s, minimum=0.0, default=0.0)
        )
        poll = (
            self.default_poll_interval_s
            if poll_interval_s is None
            else _safe_float(poll_interval_s, minimum=0.2, default=1.0)
        )

        sync_state = self.trigger_external_sync(session)
        has_staging_source = bool(
            self.capture_staging_dir
            and self.capture_staging_dir.exists()
            and self.capture_staging_dir.is_dir()
        )
        has_external_source = bool(sync_state.get("configured") or has_staging_source)

        imported = self._import_from_staging(session)
        files = self._list_files(session.session_dir)
        logger.info(
            "Warehouse capture file check: have=%s need=%s staging_imported=%s timeout_s=%s",
            len(files),
            needed,
            imported,
            timeout if has_external_source else 0.0,
        )
        if needed > 0 and len(files) >= needed and imported == 0 and not has_external_source:
            logger.debug(
                "Capture files already present in session dir (%s); staging import not required.",
                session.session_dir,
            )
        if needed <= 0 or len(files) >= needed or not has_external_source:
            return files

        deadline = time.monotonic() + timeout
        last_count = len(files)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            time.sleep(min(poll, remaining))
            imported = self._import_from_staging(session)
            files = self._list_files(session.session_dir)
            if len(files) != last_count or imported:
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

    async def wait_for_files_async(
        self,
        session: FlightCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
    ) -> list[Path]:
        """Async-safe wrapper for FastAPI/async routes.

        The original wait_for_files API is intentionally synchronous for backward
        compatibility. Use this wrapper when calling from an event loop so the
        blocking polling and filesystem work run in a worker thread.
        """
        return await run_blocking(
            self.wait_for_files,
            session,
            min_files=min_files,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            boundary="filesystem",
            operation="warehouse_capture_wait",
            call_timeout_s=max(30.0, float(timeout_s or self.default_wait_timeout_s) + 30.0),
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
        expected_min_files = self._expected_min_files(min_files)
        self.wait_for_files(
            session,
            min_files=min_files,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        ended_at = datetime.now(UTC)
        all_files = self._list_files(session.session_dir)
        image_count = sum(1 for p in all_files if p.suffix.lower() in IMAGE_EXTENSIONS)
        status = "ready" if len(all_files) >= expected_min_files else "incomplete"
        mission_kind = ""
        if extra_meta and extra_meta.get("mission_kind") is not None:
            mission_kind = str(extra_meta.get("mission_kind") or "").strip()
        if mission_kind == "warehouse_scan" and status == "ready":
            status = "staged"

        result: dict[str, Any] = {
            "flight_id": session.flight_id,
            "source_dir": session.relative_source_dir,
            "absolute_dir": str(session.session_dir),
            "started_at": self._iso(session.started_at),
            "ended_at": self._iso(ended_at),
            "file_count": len(all_files),
            "image_count": image_count,
            "files": [str(p) for p in all_files],
            "status": status,
            "min_files_expected": expected_min_files,
        }
        if extra_meta:
            result["meta"] = dict(extra_meta)
        self._write_manifest(session, result)
        self._staging_imported_by_session.pop(session.session_dir.resolve(), None)

        logger.info(
            "Warehouse capture session finalized: flight_id=%s status=%s file_count=%s manifest=%s",
            session.flight_id,
            result.get("status"),
            result.get("file_count"),
            self._manifest_path(session),
        )
        if mission_kind == "warehouse_scan":
            logger.info(
                "Warehouse scan capture session dir has %s file(s); live-map chunks and "
                "manifest are finalized separately under warehouse-live-map storage.",
                len(all_files),
            )
        return result

    async def finalize_session_async(
        self,
        session: FlightCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Async-safe wrapper around finalize_session."""
        return await run_blocking(
            self.finalize_session,
            session,
            min_files=min_files,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            extra_meta=extra_meta,
            boundary="filesystem",
            operation="warehouse_capture_finalize",
            call_timeout_s=max(30.0, float(timeout_s or self.default_wait_timeout_s) + 30.0),
        )

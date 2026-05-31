from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _default_capture_extensions() -> set[str]:
    raw = os.getenv(
        "WAREHOUSE_SCAN_CAPTURE_EXTENSIONS",
        (
            ".json,.bin,.glb,.gltf,.obj,.ply,.pcd,.las,.laz,.e57,"
            ".jpg,.jpeg,.png,.tif,.tiff,.b3dm,.pnts,"
            ".db3,.mcap,.bag,.yaml,.yml,.sqlite,.sqlite3"
        ),
    )
    values = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return values or {".json", ".bin", ".glb", ".gltf", ".obj", ".ply", ".pcd"}


@dataclass(frozen=True)
class WarehouseCaptureSession:
    flight_id: str
    relative_source_dir: str
    session_dir: Path
    started_at: datetime


class WarehouseCaptureSessionService:
    """
    Per-flight capture staging for warehouse LiDAR / SLAM outputs.

    The service intentionally mirrors the photogrammetry capture flow so the
    mission can rely on either direct-download hooks or an external sync agent.
    """

    def __init__(self) -> None:
        sync_root_raw = os.getenv("WAREHOUSE_SCAN_SYNC_DIR", "").strip() or os.getenv(
            "PHOTOGRAMMETRY_DRONE_SYNC_DIR", "backend/storage/drone_sync"
        )
        staging_raw = (
            os.getenv("WAREHOUSE_SCAN_CAPTURE_STAGING_DIR", "").strip()
            or os.getenv("PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR", "").strip()
        )

        self.sync_root = Path(sync_root_raw).resolve()
        self.capture_staging_dir = Path(staging_raw).resolve() if staging_raw else None
        self.default_wait_timeout_s = float(os.getenv("WAREHOUSE_SCAN_SYNC_TIMEOUT_S", "300"))
        self.default_poll_interval_s = float(os.getenv("WAREHOUSE_SCAN_SYNC_POLL_S", "2"))
        self.default_min_files = max(
            0,
            int(os.getenv("WAREHOUSE_SCAN_SYNC_MIN_FILES", "1")),
        )
        self.capture_sync_cmd_template = (
            os.getenv("WAREHOUSE_SCAN_CAPTURE_SYNC_CMD", "").strip()
            or os.getenv("PHOTOGRAMMETRY_CAPTURE_SYNC_CMD", "").strip()
        )
        self.capture_sync_timeout_s = float(
            os.getenv("WAREHOUSE_SCAN_CAPTURE_SYNC_TIMEOUT_S", "180")
        )
        self.allowed_extensions = _default_capture_extensions()
        self.sync_root.mkdir(parents=True, exist_ok=True)
        if self.capture_staging_dir:
            self.capture_staging_dir.mkdir(parents=True, exist_ok=True)
        self._warned_no_staging_env = False
        self._warned_missing_staging_dir = False
        self._sync_triggered_for_session: set[str] = set()

    @staticmethod
    def _sanitize_flight_id(raw: Any) -> str:
        token = _UNSAFE_TOKEN_CHARS.sub("_", str(raw or "")).strip("._-")
        return token or "unknown"

    def _manifest_path(self, session: WarehouseCaptureSession) -> Path:
        return session.session_dir / "capture_session.json"

    def _write_manifest(
        self,
        session: WarehouseCaptureSession,
        payload: dict[str, Any],
    ) -> None:
        self._manifest_path(session).write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

    def start_session(self, *, flight_id: Any) -> WarehouseCaptureSession:
        safe_flight_id = self._sanitize_flight_id(flight_id)
        relative_dir = f"flight_{safe_flight_id}"
        session_dir = (self.sync_root / relative_dir).resolve()
        try:
            session_dir.relative_to(self.sync_root)
        except ValueError:
            raise RuntimeError("Resolved warehouse capture directory is outside sync root.") from None
        session_dir.mkdir(parents=True, exist_ok=True)

        session = WarehouseCaptureSession(
            flight_id=safe_flight_id,
            relative_source_dir=relative_dir,
            session_dir=session_dir,
            started_at=_utc_now(),
        )
        self._write_manifest(
            session,
            {
                "flight_id": session.flight_id,
                "source_dir": session.relative_source_dir,
                "status": "started",
                "started_at": _iso(session.started_at),
                "file_count": 0,
            },
        )
        return session

    def _is_relevant_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.name == "capture_session.json":
            return False
        return path.suffix.lower() in self.allowed_extensions

    def _list_capture_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        files = [p for p in root.rglob("*") if self._is_relevant_file(p)]
        return sorted(files)

    @staticmethod
    def _copy_into_session(session_dir: Path, src: Path) -> Path:
        stamp = datetime.utcfromtimestamp(src.stat().st_mtime).strftime("%Y%m%d%H%M%S%f")
        dst = session_dir / f"{stamp}_{src.name}"
        if not dst.exists():
            shutil.copy2(src, dst)
        return dst

    def _import_from_staging(self, session: WarehouseCaptureSession) -> int:
        staging_dir = self.capture_staging_dir
        if staging_dir is None:
            if not self._warned_no_staging_env:
                logger.warning(
                    "WAREHOUSE_SCAN_CAPTURE_STAGING_DIR not set. "
                    "Expect an external sync process to write directly into %s",
                    session.session_dir,
                )
                self._warned_no_staging_env = True
            return 0

        if not staging_dir.exists() or not staging_dir.is_dir():
            if not self._warned_missing_staging_dir:
                logger.warning(
                    "WAREHOUSE_SCAN_CAPTURE_STAGING_DIR=%s is unavailable.",
                    staging_dir,
                )
                self._warned_missing_staging_dir = True
            return 0

        start_ts = session.started_at.timestamp() - 1.0
        copied = 0
        for src in self._list_capture_files(staging_dir):
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
        session: WarehouseCaptureSession,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        token = session.relative_source_dir
        if not self.capture_sync_cmd_template:
            return {
                "configured": False,
                "executed": False,
                "ok": False,
                "reason": "WAREHOUSE_SCAN_CAPTURE_SYNC_CMD is not set",
            }
        if token in self._sync_triggered_for_session and not force:
            return {
                "configured": True,
                "executed": False,
                "ok": True,
                "reason": "already_triggered",
            }

        rendered = self.capture_sync_cmd_template.format(
            flight_id=session.flight_id,
            source_dir=session.relative_source_dir,
            session_dir=str(session.session_dir),
            sync_root=str(self.sync_root),
            staging_dir=str(self.capture_staging_dir or ""),
        )
        argv = shlex.split(rendered)
        if not argv:
            return {
                "configured": True,
                "executed": False,
                "ok": False,
                "reason": "rendered sync command is empty",
            }

        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=max(1.0, self.capture_sync_timeout_s),
                check=False,
            )
            duration_s = round(time.monotonic() - started, 3)
            self._sync_triggered_for_session.add(token)
            return {
                "configured": True,
                "executed": True,
                "ok": proc.returncode == 0,
                "command": argv[0],
                "returncode": int(proc.returncode),
                "duration_s": duration_s,
                "stdout_tail": (proc.stdout or "").strip()[-500:],
                "stderr_tail": (proc.stderr or "").strip()[-500:],
            }
        except Exception as exc:
            duration_s = round(time.monotonic() - started, 3)
            logger.warning(
                "Warehouse capture external sync failed for %s: %s",
                session.session_dir,
                exc,
            )
            return {
                "configured": True,
                "executed": True,
                "ok": False,
                "duration_s": duration_s,
                "error": str(exc),
            }

    def import_external_files(
        self,
        session: WarehouseCaptureSession,
        *,
        capture_paths: list[str] | None,
    ) -> int:
        copied = 0
        for raw in capture_paths or []:
            src = Path(str(raw)).expanduser().resolve()
            if not src.exists() or not src.is_file():
                continue
            if src.suffix.lower() not in self.allowed_extensions:
                continue
            try:
                self._copy_into_session(session.session_dir, src)
                copied += 1
            except Exception:
                continue
        return copied

    def wait_for_files(
        self,
        session: WarehouseCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
    ) -> list[Path]:
        needed = self.default_min_files if min_files is None else max(0, int(min_files))
        timeout = self.default_wait_timeout_s if timeout_s is None else max(0.0, float(timeout_s))
        poll = (
            self.default_poll_interval_s
            if poll_interval_s is None
            else max(0.2, float(poll_interval_s))
        )

        self.trigger_external_sync(session)
        self._import_from_staging(session)
        files = self._list_capture_files(session.session_dir)
        if needed <= 0 or len(files) >= needed:
            return files

        deadline = time.monotonic() + timeout
        last_count = len(files)
        while time.monotonic() < deadline:
            time.sleep(poll)
            self._import_from_staging(session)
            files = self._list_capture_files(session.session_dir)
            if len(files) != last_count:
                logger.info(
                    "Warehouse capture sync progress: %s/%s files in %s",
                    len(files),
                    needed,
                    session.session_dir,
                )
                last_count = len(files)
            if len(files) >= needed:
                break

        if needed > 0 and len(files) < needed:
            logger.warning(
                "Warehouse capture sync timeout: found %d/%d files in %s",
                len(files),
                needed,
                session.session_dir,
            )
        return files

    def finalize_session(
        self,
        session: WarehouseCaptureSession,
        *,
        min_files: int | None = None,
        timeout_s: float | None = None,
        poll_interval_s: float | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_min = self.default_min_files if min_files is None else max(0, int(min_files))
        files = self.wait_for_files(
            session,
            min_files=target_min,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        ended_at = _utc_now()
        payload: dict[str, Any] = {
            "flight_id": session.flight_id,
            "source_dir": session.relative_source_dir,
            "absolute_dir": str(session.session_dir),
            "started_at": _iso(session.started_at),
            "ended_at": _iso(ended_at),
            "file_count": len(files),
            "files": [str(p.relative_to(session.session_dir)) for p in files],
            "status": "completed" if len(files) >= target_min else "completed_missing_files",
            "min_files_expected": target_min,
        }
        if extra_meta:
            payload["meta"] = dict(extra_meta)

        self._write_manifest(session, payload)
        return payload

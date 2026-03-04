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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@dataclass(frozen=True)
class FlightCaptureSession:
    flight_id: str
    relative_source_dir: str
    session_dir: Path
    started_at: datetime


class FlightCaptureSessionService:
    """
    Prepares a per-flight local sync directory and records image-session metadata.

    Image files must be populated by one of these sources:
    1) external sync agent (rsync/LTE/wifi job) that writes into
       `PHOTOGRAMMETRY_DRONE_SYNC_DIR/flight_<flight_id>` directly, or
    2) external sync agent writing into `PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR`,
       which this service imports into the session directory.
    """

    def __init__(self) -> None:
        self.sync_root = Path(
            os.getenv("PHOTOGRAMMETRY_DRONE_SYNC_DIR", "backend/storage/drone_sync")
        ).resolve()
        staging_raw = os.getenv("PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR", "").strip()
        self.capture_staging_dir = Path(staging_raw).resolve() if staging_raw else None
        self.default_wait_timeout_s = float(
            os.getenv("PHOTOGRAMMETRY_FLIGHT_SYNC_TIMEOUT_S", "120")
        )
        self.default_poll_interval_s = float(
            os.getenv("PHOTOGRAMMETRY_FLIGHT_SYNC_POLL_S", "2")
        )
        self.default_min_images = max(
            0, int(os.getenv("PHOTOGRAMMETRY_FLIGHT_SYNC_MIN_IMAGES", "1"))
        )
        self.capture_sync_cmd_template = os.getenv("PHOTOGRAMMETRY_CAPTURE_SYNC_CMD", "").strip()
        self.capture_sync_timeout_s = float(
            os.getenv("PHOTOGRAMMETRY_CAPTURE_SYNC_TIMEOUT_S", "180")
        )
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

    def _manifest_path(self, session: FlightCaptureSession) -> Path:
        return session.session_dir / "capture_session.json"

    def _write_manifest(self, session: FlightCaptureSession, payload: Dict[str, Any]) -> None:
        manifest_path = self._manifest_path(session)
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )

    def start_session(self, *, flight_id: Any) -> FlightCaptureSession:
        safe_flight_id = self._sanitize_flight_id(flight_id)
        relative_dir = f"flight_{safe_flight_id}"
        session_dir = (self.sync_root / relative_dir).resolve()
        if not str(session_dir).startswith(str(self.sync_root)):
            raise RuntimeError("Resolved capture session directory is outside sync root.")
        session_dir.mkdir(parents=True, exist_ok=True)

        session = FlightCaptureSession(
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
                "image_count": 0,
            },
        )
        logger.info(
            "Photogrammetry capture session prepared: flight_id=%s session_dir=%s",
            session.flight_id,
            session.session_dir,
        )
        return session

    @staticmethod
    def _list_images(root: Path) -> List[Path]:
        if not root.exists():
            return []
        files = [
            p
            for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
        return sorted(files)

    @staticmethod
    def _copy_into_session(session_dir: Path, src: Path) -> Path:
        stamp = datetime.utcfromtimestamp(src.stat().st_mtime).strftime("%Y%m%d%H%M%S%f")
        dst = session_dir / f"{stamp}_{src.name}"
        if not dst.exists():
            shutil.copy2(src, dst)
        return dst

    def _import_from_staging(self, session: FlightCaptureSession) -> int:
        staging_dir = self.capture_staging_dir
        if staging_dir is None:
            if not self._warned_no_staging_env:
                logger.warning(
                    "PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR not set — no staging import will occur. "
                    "Ensure an external sync process writes images directly into %s",
                    session.session_dir,
                )
                self._warned_no_staging_env = True
            return 0
        if not staging_dir.exists() or not staging_dir.is_dir():
            if not self._warned_missing_staging_dir:
                logger.warning(
                    "PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR=%s is unavailable — staging import disabled.",
                    staging_dir,
                )
                self._warned_missing_staging_dir = True
            return 0
        start_ts = session.started_at.timestamp() - 1.0
        copied = 0
        for src in self._list_images(staging_dir):
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
    ) -> Dict[str, Any]:
        token = session.relative_source_dir
        if not self.capture_sync_cmd_template:
            return {
                "configured": False,
                "executed": False,
                "ok": False,
                "reason": "PHOTOGRAMMETRY_CAPTURE_SYNC_CMD is not set",
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
            ok = proc.returncode == 0
            result = {
                "configured": True,
                "executed": True,
                "ok": ok,
                "command": argv[0],
                "returncode": int(proc.returncode),
                "duration_s": duration_s,
                "stdout_tail": (proc.stdout or "").strip()[-500:],
                "stderr_tail": (proc.stderr or "").strip()[-500:],
            }
            if ok:
                logger.info(
                    "Photogrammetry external sync command succeeded in %.3fs for %s",
                    duration_s,
                    session.session_dir,
                )
            else:
                logger.warning(
                    "Photogrammetry external sync command failed (rc=%s) for %s",
                    proc.returncode,
                    session.session_dir,
                )
            return result
        except Exception as exc:
            duration_s = round(time.monotonic() - started, 3)
            logger.warning(
                "Photogrammetry external sync command crashed for %s: %s",
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

    def import_external_images(
        self,
        session: FlightCaptureSession,
        *,
        image_paths: List[str] | None,
    ) -> int:
        copied = 0
        for raw in image_paths or []:
            src = Path(str(raw)).expanduser().resolve()
            if not src.exists() or not src.is_file():
                continue
            if src.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                self._copy_into_session(session.session_dir, src)
                copied += 1
            except Exception:
                continue
        if copied:
            logger.info(
                "Imported %d images from direct-download source into %s",
                copied,
                session.session_dir,
            )
        return copied

    def wait_for_images(
        self,
        session: FlightCaptureSession,
        *,
        min_images: Optional[int] = None,
        timeout_s: Optional[float] = None,
        poll_interval_s: Optional[float] = None,
    ) -> List[Path]:
        needed = self.default_min_images if min_images is None else max(0, int(min_images))
        timeout = self.default_wait_timeout_s if timeout_s is None else max(0.0, float(timeout_s))
        poll = (
            self.default_poll_interval_s
            if poll_interval_s is None
            else max(0.2, float(poll_interval_s))
        )
        sync_state = self.trigger_external_sync(session)
        if sync_state.get("configured"):
            logger.info(
                "Photogrammetry sync trigger: executed=%s ok=%s reason=%s",
                sync_state.get("executed"),
                sync_state.get("ok"),
                sync_state.get("reason"),
            )
        self._import_from_staging(session)
        images = self._list_images(session.session_dir)
        logger.info(
            "Photogrammetry image wait start: have=%s need=%s timeout_s=%s poll_s=%s",
            len(images),
            needed,
            timeout,
            poll,
        )
        if needed <= 0 or len(images) >= needed:
            return images

        deadline = time.monotonic() + timeout
        last_count = len(images)
        while time.monotonic() < deadline:
            time.sleep(poll)
            self._import_from_staging(session)
            images = self._list_images(session.session_dir)
            if len(images) != last_count:
                logger.info(
                    "Photogrammetry image wait progress: %s/%s images in %s",
                    len(images),
                    needed,
                    session.session_dir,
                )
                last_count = len(images)
            if len(images) >= needed:
                break
        if needed > 0 and len(images) < needed:
            logger.warning(
                "Photogrammetry sync timeout: found %d/%d images in %s. "
                "Verify your external sync process (rsync/LTE/wifi) is running and writing to this directory.",
                len(images),
                needed,
                session.session_dir,
            )
        return images

    def finalize_session(
        self,
        session: FlightCaptureSession,
        *,
        min_images: Optional[int] = None,
        timeout_s: Optional[float] = None,
        poll_interval_s: Optional[float] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_min = self.default_min_images if min_images is None else max(0, int(min_images))
        images = self.wait_for_images(
            session,
            min_images=target_min,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        ended_at = _utc_now()

        payload: Dict[str, Any] = {
            "flight_id": session.flight_id,
            "source_dir": session.relative_source_dir,
            "absolute_dir": str(session.session_dir),
            "started_at": _iso(session.started_at),
            "ended_at": _iso(ended_at),
            "image_count": len(images),
            "images": [str(p.relative_to(session.session_dir)) for p in images],
            "status": "completed"
            if len(images) >= target_min
            else "completed_missing_images",
            "min_images_expected": target_min,
        }
        if extra_meta:
            payload["meta"] = dict(extra_meta)

        self._write_manifest(session, payload)
        logger.info(
            "Photogrammetry capture session finalized: flight_id=%s status=%s image_count=%s manifest=%s",
            session.flight_id,
            payload.get("status"),
            payload.get("image_count"),
            self._manifest_path(session),
        )
        return payload

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import topic_env


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_token(value: object) -> str:
    raw = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or ""))
    return raw.strip("._-") or "unknown"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def mapping_session_active_path(capture_root: Path) -> Path:
    override = os.getenv("WAREHOUSE_MAPPING_SESSION_ACTIVE_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return capture_root / ".mapping_session_active"


def mark_mapping_session_active(capture_root: Path, flight_id: str) -> None:
    path = mapping_session_active_path(capture_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(flight_id.strip(), encoding="utf-8")


def clear_mapping_session_active(capture_root: Path) -> None:
    path = mapping_session_active_path(capture_root)
    if path.exists():
        path.unlink()


@dataclass
class MappingSession:
    flight_id: str
    warehouse_map_id: int | None
    profile: str
    session_dir: Path
    started_at: str = field(default_factory=utc_now_iso)
    stopped_at: str | None = None
    launch_pid: int | None = None
    status: str = "running"

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "warehouse_mapping_manifest.json"

    def to_manifest(self) -> dict[str, Any]:
        return {
            "flight_id": self.flight_id,
            "warehouse_map_id": self.warehouse_map_id,
            "profile": self.profile,
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "session_dir": str(self.session_dir),
            "launch_pid": self.launch_pid,
            "topics": topic_env(),
        }

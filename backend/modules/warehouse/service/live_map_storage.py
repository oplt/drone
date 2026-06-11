from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from backend.core.config.runtime import settings

_SAFE_ID = re.compile(r"[^a-zA-Z0-9_.-]+")
_EXTENSIONS = {
    "mesh": ".glb",
    "point_cloud": ".xyz32",
    "point_cloud_rgb": ".xyzrgb32",
    "occupancy": ".vox",
    "esdf": ".vox",
    "costmap": ".grid",
}


class LiveMapStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredLiveMapChunk:
    chunk_id: str
    path: Path
    url: str
    content_type: str
    byte_size: int
    checksum_sha256: str


def _clean_id(value: str) -> str:
    cleaned = _SAFE_ID.sub("-", value.strip())[:160].strip(".-")
    if not cleaned:
        raise LiveMapStorageError("Invalid live-map chunk id.")
    return cleaned


def _root() -> Path:
    return Path(settings.warehouse_live_map_chunk_dir).resolve()


class WarehouseLiveMapChunkStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or _root()).resolve()

    async def save_upload(
        self,
        *,
        flight_id: str,
        chunk_id: str,
        kind: str,
        upload: UploadFile,
        max_bytes: int = 32 * 1024 * 1024,
    ) -> StoredLiveMapChunk:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        ext = _EXTENSIONS.get(kind, ".bin")
        content_type = upload.content_type or "application/octet-stream"
        target_dir = self.root / safe_flight
        target_dir.mkdir(parents=True, exist_ok=True)
        temp_path = target_dir / f"{safe_chunk}.uploading"
        digest = hashlib.sha256()
        total = 0

        with temp_path.open("wb") as handle:
            while True:
                block = await upload.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    temp_path.unlink(missing_ok=True)
                    raise LiveMapStorageError("Live-map chunk exceeds maximum size.")
                digest.update(block)
                handle.write(block)

        if total <= 0:
            temp_path.unlink(missing_ok=True)
            raise LiveMapStorageError("Live-map chunk is empty.")

        checksum = digest.hexdigest()
        final_path = target_dir / f"{safe_chunk}-{checksum[:16]}{ext}"
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
            return StoredLiveMapChunk(
                chunk_id=safe_chunk,
                path=final_path,
                url=f"/warehouse/live-map/{safe_flight}/chunks/{safe_chunk}/download",
                content_type=content_type,
                byte_size=final_path.stat().st_size,
                checksum_sha256=checksum,
            )
        temp_path.replace(final_path)
        return StoredLiveMapChunk(
            chunk_id=safe_chunk,
            path=final_path,
            url=f"/warehouse/live-map/{safe_flight}/chunks/{safe_chunk}/download",
            content_type=content_type,
            byte_size=total,
            checksum_sha256=checksum,
        )

    def save_chunk_metadata(
        self,
        *,
        flight_id: str,
        chunk_id: str,
        metadata: dict[str, Any],
        checksum_sha256: str | None = None,
    ) -> Path:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        target_dir = self.root / safe_flight
        target_dir.mkdir(parents=True, exist_ok=True)

        digest = (checksum_sha256 or "").strip()[:16]
        suffix = f"-{digest}" if digest else ""
        final_path = target_dir / f"{safe_chunk}{suffix}.meta.json"
        payload = {
            "chunk_id": safe_chunk,
            **metadata,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        if final_path.exists():
            try:
                if final_path.read_text(encoding="utf-8") == encoded:
                    return final_path
            except OSError:
                pass
        final_path.write_text(encoded, encoding="utf-8")
        return final_path

    def load_chunk_metadata(
        self,
        *,
        flight_id: str,
        chunk_id: str,
    ) -> dict[str, Any] | None:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        root = (self.root / safe_flight).resolve()
        if not root.exists():
            return None

        matches = sorted(
            root.glob(f"{safe_chunk}*.meta.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in matches:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def save_preview_chunk(
        self,
        *,
        flight_id: str,
        chunk_id: str,
        preview_points_m: list[list[float]],
        point_count: int | None = None,
        bbox_local_m: list[float] | None = None,
        sequence: int = 0,
    ) -> StoredLiveMapChunk:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        payload: dict[str, Any] = {
            "preview_points_m": preview_points_m,
            "point_count": point_count,
            "bbox_local_m": bbox_local_m,
            "sequence": sequence,
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if not encoded:
            raise LiveMapStorageError("Live-map preview chunk is empty.")
        digest = hashlib.sha256(encoded).hexdigest()
        target_dir = self.root / safe_flight
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / f"{safe_chunk}-{digest[:16]}.preview.json"
        final_path.write_bytes(encoded)
        return StoredLiveMapChunk(
            chunk_id=safe_chunk,
            path=final_path,
            url=f"/warehouse/live-map/{safe_flight}/chunks/{safe_chunk}/download",
            content_type="application/json",
            byte_size=len(encoded),
            checksum_sha256=digest,
        )

    def resolve(self, *, flight_id: str, chunk_id: str) -> StoredLiveMapChunk | None:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        root = (self.root / safe_flight).resolve()
        if not root.exists():
            return None
        matches = sorted(
            (
                path
                for path in root.glob(f"{safe_chunk}-*")
                if path.is_file()
                and not path.name.endswith(".meta.json")
                and not path.name.endswith(".preview.json")
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not matches:
            return None
        path = matches[0].resolve()
        if not str(path).startswith(str(root)):
            return None
        checksum = path.stem.rsplit("-", 1)[-1]
        return StoredLiveMapChunk(
            chunk_id=safe_chunk,
            path=path,
            url=f"/warehouse/live-map/{safe_flight}/chunks/{safe_chunk}/download",
            content_type="application/octet-stream",
            byte_size=path.stat().st_size,
            checksum_sha256=checksum.ljust(64, "0")[:64],
        )


warehouse_live_map_chunk_storage = WarehouseLiveMapChunkStorage()

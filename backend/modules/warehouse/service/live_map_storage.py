from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
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
    "occupancy": ".grid",
    "esdf": ".vox",
    "costmap": ".grid",
}
_CONTENT_TYPES_BY_EXT = {
    ".glb": "model/gltf-binary",
    ".xyz32": "application/vnd.live-map.xyz32",
    ".xyzrgb32": "application/vnd.live-map.xyzrgb32",
    ".vox": "application/octet-stream",
    ".grid": "application/octet-stream",
    ".json": "application/json",
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


def _clean_id(value: object) -> str:
    cleaned = _SAFE_ID.sub("-", str(value or "").strip())[:160].strip(".-")
    if not cleaned:
        raise LiveMapStorageError("Invalid live-map chunk id.")
    return cleaned


def _root() -> Path:
    return Path(settings.warehouse_live_map_chunk_dir).expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


class WarehouseLiveMapChunkStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or _root()).resolve()

    def flight_dir(self, flight_id: object) -> Path:
        """Return the sanitized on-disk directory for a flight."""
        safe_flight = _clean_id(flight_id)
        path = (self.root / safe_flight).resolve()
        if not _is_relative_to(path, self.root):
            raise LiveMapStorageError("Resolved live-map flight directory is outside storage root.")
        return path

    @staticmethod
    def extension_for_kind(kind: str) -> str:
        return _EXTENSIONS.get(kind, ".bin")

    @staticmethod
    def infer_content_type(path: Path) -> str:
        return _CONTENT_TYPES_BY_EXT.get(path.suffix.lower(), "application/octet-stream")

    def _url(self, *, safe_flight: str, safe_chunk: str) -> str:
        return f"/warehouse/live-map/{safe_flight}/chunks/{safe_chunk}/download"

    def _stored_from_path(
        self, *, safe_flight: str, safe_chunk: str, path: Path
    ) -> StoredLiveMapChunk:
        path = path.resolve()
        root = self.flight_dir(safe_flight)
        if not _is_relative_to(path, root):
            raise LiveMapStorageError("Resolved live-map chunk is outside flight directory.")
        checksum = path.stem.rsplit("-", 1)[-1]
        return StoredLiveMapChunk(
            chunk_id=safe_chunk,
            path=path,
            url=self._url(safe_flight=safe_flight, safe_chunk=safe_chunk),
            content_type=self.infer_content_type(path),
            byte_size=path.stat().st_size,
            checksum_sha256=checksum.ljust(64, "0")[:64],
        )

    async def save_upload(
        self,
        *,
        flight_id: str,
        chunk_id: str,
        frame_id: str,
        kind: str,
        upload: UploadFile,
        max_bytes: int = 32 * 1024 * 1024,
    ) -> StoredLiveMapChunk:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        if max_bytes <= 0:
            raise LiveMapStorageError("Live-map chunk maximum size must be positive.")

        ext = self.extension_for_kind(kind)
        content_type = upload.content_type or self.infer_content_type(Path(f"chunk{ext}"))
        target_dir = self.flight_dir(safe_flight)
        target_dir.mkdir(parents=True, exist_ok=True)

        fd, raw_temp = tempfile.mkstemp(
            prefix=f"{safe_chunk}.",
            suffix=".uploading",
            dir=str(target_dir),
        )
        temp_path: Path | None = Path(raw_temp)
        digest = hashlib.sha256()
        total = 0

        try:
            with os.fdopen(fd, "wb") as handle:
                while True:
                    block = await upload.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > max_bytes:
                        raise LiveMapStorageError("Live-map chunk exceeds maximum size.")
                    digest.update(block)
                    await asyncio.to_thread(handle.write, block)

            if total <= 0:
                raise LiveMapStorageError("Live-map chunk is empty.")

            checksum = digest.hexdigest()
            final_path = target_dir / f"{safe_chunk}-{checksum[:16]}{ext}"
            if final_path.exists():
                return StoredLiveMapChunk(
                    chunk_id=safe_chunk,
                    path=final_path,
                    url=self._url(safe_flight=safe_flight, safe_chunk=safe_chunk),
                    content_type=content_type,
                    byte_size=final_path.stat().st_size,
                    checksum_sha256=checksum,
                )
            assert temp_path is not None
            temp_path.replace(final_path)
            temp_path = None
            return StoredLiveMapChunk(
                chunk_id=safe_chunk,
                path=final_path,
                url=self._url(safe_flight=safe_flight, safe_chunk=safe_chunk),
                content_type=content_type,
                byte_size=total,
                checksum_sha256=checksum,
            )
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

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
        target_dir = self.flight_dir(safe_flight)
        target_dir.mkdir(parents=True, exist_ok=True)

        digest = (checksum_sha256 or "").strip()[:16]
        suffix = f"-{digest}" if digest else ""
        final_path = target_dir / f"{safe_chunk}{suffix}.meta.json"
        payload = {"chunk_id": safe_chunk, **metadata}
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if final_path.exists():
            try:
                if final_path.read_bytes() == encoded:
                    return final_path
            except OSError:
                pass
        _atomic_write_bytes(final_path, encoded)
        return final_path

    def _metadata_candidates(self, *, root: Path, safe_chunk: str) -> Iterable[Path]:
        exact = root / f"{safe_chunk}.meta.json"
        if exact.exists():
            yield exact
        yield from root.glob(f"{safe_chunk}-*.meta.json")

    def load_chunk_metadata(
        self,
        *,
        flight_id: str,
        chunk_id: str,
    ) -> dict[str, Any] | None:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        root = self.flight_dir(safe_flight)
        if not root.exists():
            return None

        matches = sorted(
            (
                path
                for path in self._metadata_candidates(root=root, safe_chunk=safe_chunk)
                if path.is_file()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in matches:
            try:
                if not _is_relative_to(path, root):
                    continue
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
        if not preview_points_m:
            raise LiveMapStorageError("Live-map preview chunk is empty.")
        safe_frame = str(frame_id or "").strip()
        if not safe_frame:
            raise LiveMapStorageError("Live-map preview frame_id is required.")
        payload: dict[str, Any] = {
            "frame_id": safe_frame,
            "preview_points_m": preview_points_m,
            "point_count": point_count,
            "bbox_local_m": bbox_local_m,
            "sequence": sequence,
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        target_dir = self.flight_dir(safe_flight)
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / f"{safe_chunk}-{digest[:16]}.preview.json"
        _atomic_write_bytes(final_path, encoded)
        return StoredLiveMapChunk(
            chunk_id=safe_chunk,
            path=final_path,
            url=self._url(safe_flight=safe_flight, safe_chunk=safe_chunk),
            content_type="application/json",
            byte_size=len(encoded),
            checksum_sha256=digest,
        )

    def resolve(self, *, flight_id: str, chunk_id: str) -> StoredLiveMapChunk | None:
        safe_flight = _clean_id(flight_id)
        safe_chunk = _clean_id(chunk_id)
        root = self.flight_dir(safe_flight)
        if not root.exists():
            return None

        latest: Path | None = None
        latest_mtime = -1.0
        for path in root.glob(f"{safe_chunk}-*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if (
                name.endswith(".meta.json")
                or name.endswith(".preview.json")
                or name.endswith(".uploading")
            ):
                continue
            if not _is_relative_to(path, root):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest = path
                latest_mtime = mtime

        if latest is None:
            return None
        return self._stored_from_path(safe_flight=safe_flight, safe_chunk=safe_chunk, path=latest)

    def iter_chunk_files(self, *, flight_id: str) -> list[StoredLiveMapChunk]:
        """Return latest persisted non-preview/non-sidecar chunk files for a flight."""
        safe_flight = _clean_id(flight_id)
        root = self.flight_dir(safe_flight)
        if not root.exists() or not root.is_dir():
            return []

        latest_by_chunk: dict[str, tuple[float, Path]] = {}
        for path in root.iterdir():
            if not path.is_file():
                continue
            name = path.name.lower()
            if (
                name.endswith(".meta.json")
                or name.endswith(".preview.json")
                or name.endswith(".uploading")
            ):
                continue
            stem = path.stem
            if "-" not in stem:
                continue
            chunk = stem.rsplit("-", 1)[0]
            try:
                safe_chunk = _clean_id(chunk)
                mtime = path.stat().st_mtime
            except (LiveMapStorageError, OSError):
                continue
            existing = latest_by_chunk.get(safe_chunk)
            if existing is None or mtime > existing[0]:
                latest_by_chunk[safe_chunk] = (mtime, path)

        stored: list[StoredLiveMapChunk] = []
        for safe_chunk, (_mtime, path) in latest_by_chunk.items():
            try:
                stored.append(
                    self._stored_from_path(
                        safe_flight=safe_flight, safe_chunk=safe_chunk, path=path
                    )
                )
            except (OSError, LiveMapStorageError):
                continue
        return sorted(stored, key=lambda item: item.path.name)


warehouse_live_map_chunk_storage = WarehouseLiveMapChunkStorage()

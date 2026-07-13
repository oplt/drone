"""Bounded image-upload validation and persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiofiles


def validate_image_metadata(upload: Any, *, allowed_extensions: set[str]) -> str:
    filename = Path(getattr(upload, "filename", None) or "capture.jpg").name
    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        raise ValueError("Supported capture formats: JPG, PNG, TIFF, and WEBP.")
    content_type = str(getattr(upload, "content_type", "") or "")
    if content_type and not content_type.startswith("image/"):
        raise ValueError("Capture upload must be an image.")
    return extension


async def write_bounded_upload(upload: Any, destination: Path, *, max_bytes: int) -> int:
    return await write_bounded_image_upload(
        upload,
        destination,
        max_bytes=max_bytes,
        extension=None,
    )


def _matches_image_signature(extension: str, header: bytes) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".tif", ".tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    if extension == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


async def write_bounded_image_upload(
    upload: Any,
    destination: Path,
    *,
    max_bytes: int,
    extension: str | None,
) -> int:
    """Stream bounded image bytes; validate signature without decoding pixels."""
    first_chunk = await upload.read(1024 * 1024)
    if not first_chunk:
        raise ValueError("Capture upload is empty.")
    size = len(first_chunk)
    if size > max_bytes:
        raise ValueError(f"Capture exceeds {max_bytes // (1024 * 1024)} MB limit.")
    if extension is not None and not _matches_image_signature(extension, first_chunk[:12]):
        raise ValueError("Capture content does not match its image extension.")

    async with aiofiles.open(destination, "wb") as output:
        await output.write(first_chunk)
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"Capture exceeds {max_bytes // (1024 * 1024)} MB limit.")
            await output.write(chunk)
    return size

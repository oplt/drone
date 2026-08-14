"""Live-map flight manifest — chunk storage access."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .chunk_ids import _chunk_id_from_path
from .deps import resolve_chunk_storage


def _flight_root(flight_id: str) -> Path:
    storage = resolve_chunk_storage()
    if hasattr(storage, "flight_dir"):
        return storage.flight_dir(flight_id)  # type: ignore[attr-defined]
    return (storage.root / str(flight_id).strip()).resolve()


def _iter_stored_chunks(flight_id: str) -> Iterable[Any]:
    storage = resolve_chunk_storage()
    if hasattr(storage, "iter_chunk_files"):
        yield from storage.iter_chunk_files(flight_id=flight_id)  # type: ignore[attr-defined]
        return
    root = _flight_root(flight_id)
    if not root.exists():
        return
    seen: set[str] = set()
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        chunk_id = _chunk_id_from_path(path)
        if chunk_id is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        stored = storage.resolve(flight_id=flight_id, chunk_id=chunk_id)
        if stored is not None:
            yield stored


__all__ = ["_flight_root", "_iter_stored_chunks"]

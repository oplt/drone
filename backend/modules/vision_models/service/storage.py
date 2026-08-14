from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from backend.modules.vision_models.config import vision_settings

VISION_URI_PREFIX = "vision://"


class VisionStorageError(ValueError):
    pass


class VisionStorage:
    """Resolve managed local artifacts without exposing filesystem paths to clients."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or vision_settings.vision_storage_dir).resolve()

    def project_path(self, project_id: str, *parts: str) -> Path:
        if not project_id or "/" in project_id or "\\" in project_id:
            raise VisionStorageError("Invalid project identifier")
        return self._within_root("projects", project_id, *parts)

    def _within_root(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts).resolve()
        if path != self.root and self.root not in path.parents:
            raise VisionStorageError("Artifact path escapes managed storage")
        return path

    def to_uri(self, path: str | Path) -> str:
        resolved = Path(path).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise VisionStorageError("Artifact is outside managed storage")
        return f"{VISION_URI_PREFIX}{resolved.relative_to(self.root).as_posix()}"

    def resolve_uri(self, uri: str) -> Path:
        if not uri.startswith(VISION_URI_PREFIX):
            raise VisionStorageError("Unsupported vision artifact URI")
        relative = PurePosixPath(uri.removeprefix(VISION_URI_PREFIX))
        if relative.is_absolute() or ".." in relative.parts:
            raise VisionStorageError("Invalid vision artifact URI")
        return self._within_root(*relative.parts)

    def resolve_backend_key(self, backend_key: str) -> Path:
        relative = PurePosixPath(backend_key)
        if relative.is_absolute() or ".." in relative.parts:
            raise VisionStorageError("Invalid vision storage key")
        return self._within_root(*relative.parts)

    def resolve_registered(
        self, *, backend_key: str | None, legacy_uri: str | None
    ) -> Path:
        if backend_key:
            return self.resolve_backend_key(backend_key)
        if legacy_uri:
            return self.resolve_uri(legacy_uri)
        raise VisionStorageError("Vision artifact has no storage location")

    def remove_project(self, project_id: str) -> None:
        path = self.project_path(project_id)
        if path.exists():
            shutil.rmtree(path)


vision_storage = VisionStorage()

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from backend.modules.video_analysis.schemas import BUILTIN_MODEL_NAMES, CUSTOM_MODEL_PREFIX

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = BACKEND_ROOT / "storage" / "ml_models"
BUILTIN_MODEL_ROOT = MODEL_ROOT / "ultralytics"


class ModelArtifactIntegrityError(RuntimeError):
    """The bytes on disk do not match the registered immutable artifact."""


@dataclass(frozen=True, slots=True)
class ResolvedModelArtifact:
    path: Path
    artifact_hash: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_model_path(model_name: str) -> Path:
    """Resolve validated API model values into backend-managed storage paths."""
    if model_name in BUILTIN_MODEL_NAMES:
        BUILTIN_MODEL_ROOT.mkdir(parents=True, exist_ok=True)
        return BUILTIN_MODEL_ROOT / model_name
    if model_name.startswith(CUSTOM_MODEL_PREFIX):
        relative = model_name.removeprefix("backend/")
        target = (BACKEND_ROOT / relative).resolve()
        if MODEL_ROOT.resolve() not in target.parents:
            raise ValueError("Custom model path escapes managed model storage")
        return target
    raise ValueError(f"Unsupported video analysis model: {model_name}")


def _download_builtin_model(target_path: Path) -> None:
    from ultralytics.utils.downloads import attempt_download_asset

    # Passing the absolute managed path makes Ultralytics download there,
    # instead of creating a weight file in the worker's current directory.
    attempt_download_asset(str(target_path))


def ensure_model_file(model_name: str) -> Path:
    """Return local model path, downloading missing built-in weights in managed storage."""
    target_path = resolve_model_path(model_name)
    if model_name in BUILTIN_MODEL_NAMES and not target_path.is_file():
        _download_builtin_model(target_path)
    if not target_path.is_file():
        raise FileNotFoundError(f"Model weights not found at {target_path}")
    return target_path


def resolve_model_artifact(
    model_name: str,
    *,
    model_path: str | Path | None = None,
    expected_checksum: str | None = None,
) -> ResolvedModelArtifact:
    """Resolve and verify model bytes before they are handed to a runtime."""
    path = Path(model_path) if model_path is not None else ensure_model_file(model_name)
    if not path.is_file():
        raise FileNotFoundError("Model weights are unavailable")
    path = path.resolve()
    artifact_hash = sha256_file(path)
    if expected_checksum is not None and artifact_hash != expected_checksum.lower():
        raise ModelArtifactIntegrityError(
            "Registered model artifact checksum mismatch; refusing to load mutated weights."
        )
    return ResolvedModelArtifact(path=path, artifact_hash=artifact_hash)

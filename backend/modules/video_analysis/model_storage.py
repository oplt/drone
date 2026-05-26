from __future__ import annotations

from pathlib import Path

from backend.modules.video_analysis.schemas import BUILTIN_MODEL_NAMES, CUSTOM_MODEL_PREFIX

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = BACKEND_ROOT / "storage" / "ml_models"
BUILTIN_MODEL_ROOT = MODEL_ROOT / "ultralytics"


def resolve_model_path(model_name: str) -> Path:
    """Resolve validated API model values into backend-managed storage paths."""
    if model_name in BUILTIN_MODEL_NAMES:
        BUILTIN_MODEL_ROOT.mkdir(parents=True, exist_ok=True)
        return BUILTIN_MODEL_ROOT / model_name
    if model_name.startswith(CUSTOM_MODEL_PREFIX):
        return BACKEND_ROOT / model_name
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

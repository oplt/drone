from __future__ import annotations

import inspect
from pathlib import Path

from backend.modules.patrol.vision.runtime import MLRuntimeManager


def test_requirements_exclude_legacy_password_hashers() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    for name in ("requirements.txt", "requirements-api.txt", "requirements-workers-ml.txt"):
        text = (backend_root / name).read_text(encoding="utf-8").lower()
        assert "passlib" not in text
        assert "bcrypt" not in text


def test_api_requirements_exclude_worker_ml_stack() -> None:
    from backend.scripts.check_dependency_gates import _read_requirement_names

    api_names = _read_requirement_names(
        Path(__file__).resolve().parents[1] / "requirements-api.txt"
    )
    for package in ("torch", "ultralytics", "ultralytics-thop", "sahi", "supervision"):
        assert package not in api_names


def test_identity_service_uses_argon2_only() -> None:
    from backend.modules import identity

    source = inspect.getsource(identity.service)
    assert "argon2" in source
    assert "passlib" not in source
    assert "bcrypt" not in source


def test_ml_runtime_defers_pipeline_construction() -> None:
    source = inspect.getsource(MLRuntimeManager)
    assert "DroneAnomalyPipeline()" in source
    assert "def _get_pipeline" in source
    init_source = inspect.getsource(MLRuntimeManager.__init__)
    assert "DroneAnomalyPipeline()" not in init_source

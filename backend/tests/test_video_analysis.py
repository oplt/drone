from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from backend.modules.video_analysis import model_storage
from backend.modules.video_analysis.schemas import AnalyzeVideoRequest
from backend.modules.video_analysis.service import frame_extractor


class _FakeCapture:
    def __init__(self) -> None:
        self.position = 0
        self.seeks: list[int] = []

    def isOpened(self) -> bool:
        return True

    def get(self, key: int) -> float:
        if key == frame_extractor.cv2.CAP_PROP_FPS:
            return 30.0
        if key == frame_extractor.cv2.CAP_PROP_FRAME_COUNT:
            return 301.0
        return 0.0

    def set(self, key: int, value: float) -> bool:
        if key == frame_extractor.cv2.CAP_PROP_POS_FRAMES:
            self.position = int(value)
            self.seeks.append(self.position)
        return True

    def read(self):
        return True, np.zeros((2, 2, 3), dtype=np.uint8)

    def release(self) -> None:
        pass


def test_sparse_video_sampling_seeks_only_target_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _FakeCapture()
    monkeypatch.setattr(frame_extractor.cv2, "VideoCapture", lambda _: capture)

    frames = list(frame_extractor.iter_frames(Path("flight.mp4"), every_seconds=2.0))

    assert [frame.frame_index for frame in frames] == [0, 60, 120, 180, 240, 300]
    assert capture.seeks == [0, 60, 120, 180, 240, 300]


def test_model_name_must_be_allowlisted() -> None:
    with pytest.raises(ValueError):
        AnalyzeVideoRequest(model_name="https://untrusted.invalid/model.pt")


def test_default_model_is_yolo26s() -> None:
    assert AnalyzeVideoRequest().model_name == "yolo26s.pt"


def test_agriculture_model_uses_local_storage_path() -> None:
    request = AnalyzeVideoRequest(model_name="storage/ml_models/agriculture/best.pt")

    assert request.model_name == "storage/ml_models/agriculture/best.pt"


def test_custom_model_cannot_escape_local_storage() -> None:
    with pytest.raises(ValueError):
        AnalyzeVideoRequest(model_name="storage/ml_models/../../remote.pt")


def test_download_script_prewarms_yolo26_models() -> None:
    script = Path("backend/scripts/download_video_analysis_models.py").read_text()

    for model in ("yolo26n.pt", "yolo26s.pt", "yolo26n-seg.pt", "yolo26s-seg.pt"):
        assert model in script


def test_builtin_model_resolves_under_backend_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_storage, "BUILTIN_MODEL_ROOT", tmp_path / "ultralytics")

    path = model_storage.resolve_model_path("yolo26s.pt")

    assert path == tmp_path / "ultralytics" / "yolo26s.pt"
    assert path.parent.is_dir()


def test_custom_model_resolves_under_backend_storage() -> None:
    path = model_storage.resolve_model_path("storage/ml_models/agriculture/best.pt")

    assert path == model_storage.BACKEND_ROOT / "storage/ml_models/agriculture/best.pt"


def test_missing_builtin_model_downloads_to_managed_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed_root = tmp_path / "backend" / "storage" / "ml_models" / "ultralytics"
    downloaded_to: list[Path] = []

    def fake_download(target_path: Path) -> None:
        downloaded_to.append(target_path)
        target_path.write_bytes(b"weights")

    monkeypatch.setattr(model_storage, "BUILTIN_MODEL_ROOT", managed_root)
    monkeypatch.setattr(model_storage, "_download_builtin_model", fake_download)

    path = model_storage.ensure_model_file("yolo26s.pt")

    assert path == managed_root / "yolo26s.pt"
    assert downloaded_to == [managed_root / "yolo26s.pt"]
    assert path.is_file()


def test_existing_builtin_model_is_not_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    managed_root = tmp_path / "ultralytics"
    managed_root.mkdir()
    model_path = managed_root / "yolo26s.pt"
    model_path.write_bytes(b"weights")

    monkeypatch.setattr(model_storage, "BUILTIN_MODEL_ROOT", managed_root)
    monkeypatch.setattr(
        model_storage,
        "_download_builtin_model",
        lambda _: pytest.fail("existing managed weight must not download"),
    )

    assert model_storage.ensure_model_file("yolo26s.pt") == model_path


def test_builtin_downloader_receives_absolute_managed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = ModuleType("ultralytics.utils.downloads")
    requested: list[str] = []
    downloads.attempt_download_asset = requested.append  # type: ignore[attr-defined]
    utils = ModuleType("ultralytics.utils")
    utils.__path__ = []  # type: ignore[attr-defined]
    ultralytics = ModuleType("ultralytics")
    ultralytics.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics)
    monkeypatch.setitem(sys.modules, "ultralytics.utils", utils)
    monkeypatch.setitem(sys.modules, "ultralytics.utils.downloads", downloads)
    target_path = (tmp_path / "backend/storage/ml_models/ultralytics/yolo26s.pt").resolve()

    model_storage._download_builtin_model(target_path)

    assert requested == [str(target_path)]

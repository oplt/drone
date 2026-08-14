from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from backend.modules.vision_models.config import VisionRuntimeSettings
from backend.modules.vision_models.service.trainers.base import TrainerRequest
from backend.modules.vision_models.service.trainers.ultralytics import UltralyticsTrainer


def test_vision_training_dataloader_workers_default() -> None:
    settings = VisionRuntimeSettings(_env_file=None)
    assert settings.vision_training_dataloader_workers == 0


def test_vision_training_dataloader_workers_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VISION_TRAINING_DATALOADER_WORKERS", "4")
    settings = VisionRuntimeSettings(_env_file=None)
    assert settings.vision_training_dataloader_workers == 4


def test_vision_training_dataloader_workers_rejects_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VISION_TRAINING_DATALOADER_WORKERS", "-1")
    with pytest.raises(ValueError):
        VisionRuntimeSettings(_env_file=None)


def test_ultralytics_trainer_passes_dataloader_workers_to_train(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def add_callback(self, *_args: object, **_kwargs: object) -> None:
            return None

        def train(self, **kwargs: object) -> None:
            captured.update(kwargs)
            project = Path(str(kwargs["project"]))
            name = str(kwargs["name"])
            weights = project / name / "weights" / "best.pt"
            weights.parent.mkdir(parents=True, exist_ok=True)
            weights.write_bytes(b"best")

        def val(self, **kwargs: object) -> SimpleNamespace:
            captured["val_kwargs"] = kwargs
            return SimpleNamespace(
                results_dict={
                    "metrics/precision(B)": 0.5,
                    "metrics/recall(B)": 0.5,
                    "metrics/mAP50(B)": 0.5,
                    "metrics/mAP50-95(B)": 0.4,
                },
                box=None,
                confusion_matrix=None,
                per_image_stats=[],
            )

    torch_mod = ModuleType("torch")
    torch_mod.cuda = SimpleNamespace(is_available=lambda: False)
    ultralytics_mod = ModuleType("ultralytics")
    ultralytics_mod.YOLO = lambda _path: FakeModel()
    monkeypatch.setitem(sys.modules, "torch", torch_mod)
    monkeypatch.setitem(sys.modules, "ultralytics", ultralytics_mod)
    monkeypatch.setattr(
        "backend.modules.vision_models.service.trainers.ultralytics.ensure_model_file",
        lambda _model: tmp_path / "base.pt",
    )
    (tmp_path / "base.pt").write_bytes(b"base")
    data_config = tmp_path / "data.yaml"
    data_config.write_text("path: .\n", encoding="utf-8")

    UltralyticsTrainer().train(
        TrainerRequest(
            base_model="yolo26n.pt",
            data_config=data_config,
            output_dir=tmp_path / "run",
            epochs=1,
            image_size=640,
            batch_size=2,
            requested_device="cpu",
            class_names=["ripe"],
            dataloader_workers=3,
        ),
        lambda *_args, **_kwargs: None,
    )

    assert captured["workers"] == 3

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.modules.vision_models import training_operations
from backend.modules.vision_models.application import VisionApplication, VisionNotFound
from backend.modules.vision_models.models import ModelVersion, TrainingRun, VisionModel
from backend.modules.vision_models.service import training_service
from backend.modules.vision_models.service.storage import VisionStorage
from backend.modules.vision_models.service.trainers.base import TrainerResult
from backend.modules.vision_models.service.training_service import VisionTrainingService


def training_run() -> SimpleNamespace:
    now = datetime.now(UTC)
    project = SimpleNamespace(
        id="project-1",
        org_id=7,
        name="Tomato detector",
        crop="tomato",
        task_type="detection",
        classes=[SimpleNamespace(name="ripe", class_index=0)],
    )
    dataset = SimpleNamespace(
        id="dataset-1",
        version=1,
        manifest_checksum="a" * 64,
        images=[],
    )
    return SimpleNamespace(
        id="run-1",
        project=project,
        project_id=project.id,
        dataset=dataset,
        dataset_id=dataset.id,
        model_version=None,
        status="queued",
        started_at=None,
        finished_at=None,
        error=None,
        progress=0.0,
        current_epoch=0,
        metrics={},
        base_model="yolo26n.pt",
        preset="balanced",
        epochs=5,
        image_size=640,
        batch_size=2,
        device="auto",
        created_at=now,
    )


class FakeTrainingDatabase:
    def __init__(self, run: SimpleNamespace):
        self.run = run
        self.model: VisionModel | None = None
        self.version: ModelVersion | None = None
        self.scalar_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.run)

    async def scalar(self, _statement):
        self.scalar_calls += 1
        return self.model if self.scalar_calls == 1 else 0

    def add(self, value):
        if isinstance(value, VisionModel):
            value.id = value.id or "model-1"
            self.model = value
        if isinstance(value, ModelVersion):
            value.id = value.id or "version-1"
            self.version = value
            self.run.model_version = value

    async def flush(self):
        if self.model is not None and not self.model.id:
            self.model.id = "model-1"

    async def refresh(self, _value):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def get(self, model, identifier):
        if model is TrainingRun and identifier == self.run.id:
            return self.run
        return None


class FakeTrainer:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def train(self, request, _progress_callback):
        if self.fail:
            raise RuntimeError("evaluation exploded")
        request.output_dir.mkdir(parents=True, exist_ok=True)
        best = request.output_dir / "best.pt"
        best.write_bytes(b"trained weights")
        confusion = request.output_dir / "confusion_matrix.png"
        confusion.write_bytes(b"png")
        return TrainerResult(
            best_weights=best,
            device="cpu",
            metrics={
                "summary": {
                    "precision": 0.91,
                    "recall": 0.82,
                    "map50": 0.88,
                    "map75": 0.71,
                    "map50_95": 0.63,
                },
                "per_class": [{"class_name": "ripe", "map50": 0.88}],
                "confusion_matrix": [[8, 1], [2, 0]],
                "confusion_matrix_labels": ["ripe", "background"],
                "per_image": [{"image_name": "hard.jpg", "fn": 2}],
            },
            evaluation_artifacts={"confusion_matrix": confusion},
        )


async def run_inline(function, *args, **kwargs):
    return function(*args, **kwargs)


@pytest.mark.asyncio
async def test_fake_training_persists_real_shaped_evaluation_and_artifacts(
    tmp_path, monkeypatch
):
    run = training_run()
    database = FakeTrainingDatabase(run)
    monkeypatch.setattr(training_service, "Session", lambda: database)
    monkeypatch.setattr(training_service.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        training_service,
        "build_yolo_dataset",
        lambda **_kwargs: tmp_path / "dataset.yaml",
    )
    service = VisionTrainingService(
        trainer=FakeTrainer(), storage=VisionStorage(tmp_path / "vision")
    )

    result = await service.run(run.id)

    assert result == {"run_id": run.id, "model_version_id": "version-1"}
    assert run.status == "completed"
    assert database.version is not None
    assert database.version.metrics["summary"]["map75"] == pytest.approx(0.71)
    assert database.version.metrics["per_image"][0]["fn"] == 2
    artifact_uri = database.version.evaluation_artifacts["confusion_matrix"]
    assert service.storage.resolve_uri(artifact_uri).read_bytes() == b"png"


@pytest.mark.asyncio
async def test_training_evaluation_failure_marks_run_failed(tmp_path, monkeypatch):
    run = training_run()
    database = FakeTrainingDatabase(run)
    monkeypatch.setattr(training_service, "Session", lambda: database)
    monkeypatch.setattr(training_service.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        training_service,
        "build_yolo_dataset",
        lambda **_kwargs: tmp_path / "dataset.yaml",
    )
    service = VisionTrainingService(
        trainer=FakeTrainer(fail=True), storage=VisionStorage(tmp_path / "vision")
    )

    with pytest.raises(RuntimeError, match="evaluation exploded"):
        await service.run(run.id)

    assert run.status == "failed"
    assert run.error == "evaluation exploded"
    assert database.version is None


@pytest.mark.asyncio
async def test_evaluation_contract_is_tenant_scoped_and_missing_artifacts_404(
    tmp_path, monkeypatch
):
    run = training_run()
    run.dataset.image_count = 6
    run.dataset.test_count = 1
    version = SimpleNamespace(
        id="version-1",
        dataset_id=run.dataset.id,
        version=1,
        model=SimpleNamespace(name="Tomato detector"),
        training_run=run,
        metrics={
            "summary": {"map50": 0.88},
            "per_class": [{"class_name": "ripe", "map50": 0.88}],
            "confusion_matrix": [[4, 1], [0, 0]],
            "confusion_matrix_labels": ["ripe", "background"],
        },
        evaluation_artifacts={"confusion_matrix": "vision://missing.png"},
    )

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_model_version(self, version_id, user, **_kwargs):
            if version_id == version.id and user.org_id == 7:
                return version
            return None

    class FakeDatabase:
        async def get(self, model, identifier):
            if identifier == run.dataset.id:
                return run.dataset
            return None

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)
    application = VisionApplication(storage=VisionStorage(tmp_path))
    allowed_user = SimpleNamespace(id=1, org_id=7)
    evaluation = await application.get_evaluation(
        FakeDatabase(), version.id, allowed_user
    )
    assert evaluation.summary["map50"] == pytest.approx(0.88)
    assert evaluation.test_image_count == 1
    assert evaluation.split == "test"

    with pytest.raises(VisionNotFound, match="artifact"):
        await application.resolve_evaluation_artifact(
            FakeDatabase(), version.id, "confusion_matrix", allowed_user
        )
    with pytest.raises(VisionNotFound, match="Model version"):
        await application.get_evaluation(
            FakeDatabase(), version.id, SimpleNamespace(id=2, org_id=8)
        )
    with pytest.raises(VisionNotFound, match="Model version"):
        await application.get_evaluation(FakeDatabase(), "missing", allowed_user)

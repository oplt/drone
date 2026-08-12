from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from backend.modules.vision_models import training_operations
from backend.modules.vision_models.application import VisionApplication, VisionNotFound
from backend.modules.vision_models.models import ModelVersion, TrainingRun, VisionModel
from backend.modules.vision_models.schemas import TrainingRunCreate
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
        attempt=0,
        lease_owner=None,
        heartbeat_at=None,
        lease_expires_at=None,
        terminal_reason_code=None,
        terminal_stage=None,
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
        if isinstance(_statement, Update):
            for column, value in _statement._values.items():
                setattr(self.run, column.key, getattr(value, "value", value))
            return SimpleNamespace(
                rowcount=1,
                scalar_one_or_none=lambda: None,
            )
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


def install_fake_lease(monkeypatch, run):
    async def claim(run_id, owner):
        assert run_id == run.id
        if run.status != "queued":
            return None
        run.status = "running"
        run.attempt += 1
        run.lease_owner = owner
        return run.attempt

    async def checkpoint(run_id, *, lease_owner, attempt, **_kwargs):
        assert run_id == run.id
        assert lease_owner == run.lease_owner
        assert attempt == run.attempt

    monkeypatch.setattr(training_service, "claim_training_run", claim)
    monkeypatch.setattr(training_service, "training_checkpoint", checkpoint)


@pytest.mark.asyncio
async def test_fake_training_persists_real_shaped_evaluation_and_artifacts(
    tmp_path, monkeypatch
):
    run = training_run()
    install_fake_lease(monkeypatch, run)
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
    install_fake_lease(monkeypatch, run)
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
async def test_duplicate_training_delivery_exits_without_second_publish(
    tmp_path, monkeypatch
):
    run = training_run()
    install_fake_lease(monkeypatch, run)
    database = FakeTrainingDatabase(run)
    monkeypatch.setattr(training_service, "Session", lambda: database)
    monkeypatch.setattr(training_service.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        training_service,
        "build_yolo_dataset",
        lambda **_kwargs: tmp_path / "dataset.yaml",
    )
    trainer = FakeTrainer()
    service = VisionTrainingService(
        trainer=trainer, storage=VisionStorage(tmp_path / "vision")
    )

    first = await service.run(run.id, lease_owner="worker-1")
    second = await service.run(run.id, lease_owner="worker-2")

    assert first["model_version_id"] == "version-1"
    assert second == {"run_id": run.id, "model_version_id": "version-1"}
    assert database.version is run.model_version


@pytest.mark.asyncio
async def test_cancel_between_epochs_prevents_model_publish(tmp_path, monkeypatch):
    run = training_run()
    install_fake_lease(monkeypatch, run)
    database = FakeTrainingDatabase(run)
    monkeypatch.setattr(training_service, "Session", lambda: database)
    monkeypatch.setattr(
        training_service,
        "build_yolo_dataset",
        lambda **_kwargs: tmp_path / "dataset.yaml",
    )

    async def cancel_checkpoint(*_args, **_kwargs):
        run.status = "cancelled"
        run.lease_owner = None
        raise training_service.TrainingCancelled()

    monkeypatch.setattr(training_service, "training_checkpoint", cancel_checkpoint)

    class EpochTrainer(FakeTrainer):
        def train(self, request, progress_callback):
            progress_callback(1, request.epochs, {"loss": 0.5})
            raise AssertionError("cancelled callback must stop training")

    service = VisionTrainingService(
        trainer=EpochTrainer(), storage=VisionStorage(tmp_path / "vision")
    )

    result = await service.run(run.id, lease_owner="worker-1")

    assert result == {"run_id": run.id, "status": "cancelled"}
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


@pytest.mark.asyncio
async def test_locked_dataset_can_start_a_new_attempt_and_running_attempt_cancels(
    monkeypatch,
):
    now = datetime.now(UTC)
    project = SimpleNamespace(
        id="project-1",
        classes=[SimpleNamespace(name="ripe")],
    )
    dataset = SimpleNamespace(
        id="dataset-1",
        project_id=project.id,
        status="locked",
        locked_at=now,
        manifest_checksum="a" * 64,
    )
    images = [
        SimpleNamespace(selected=True, annotation_status="reviewed", split=split)
        for split in ("train", "val", "test")
    ]
    previous_run = SimpleNamespace(id="run-failed", status="failed")
    created_runs = []

    class FakeRepository:
        def __init__(self, _db):
            pass

        @staticmethod
        def project_visible_to(_user):
            return True

        async def get_project(self, project_id, _user):
            return project if project_id == project.id else None

        async def get_dataset(self, dataset_id, _user):
            return dataset if dataset_id == dataset.id else None

        async def all_dataset_images(self, dataset_id):
            return images if dataset_id == dataset.id else []

        async def get_training_run(self, run_id, _user):
            return next((run for run in created_runs if run.id == run_id), None)

    class FakeQueue:
        def __init__(self):
            self.revoked = []

        def enqueue(self, run_id):
            return f"task-{run_id}"

        def revoke(self, task_id):
            self.revoked.append(task_id)

    class FakeDatabase:
        async def scalar(self, _statement):
            return 0

        def add(self, value):
            if isinstance(value, TrainingRun):
                value.id = "run-retry"
                value.progress = 0.0
                value.current_epoch = 0
                value.metrics = {}
                value.error = None
                value.queue_task_id = None
                value.started_at = None
                value.finished_at = None
                value.created_at = now
                value.model_version = None
                created_runs.append(value)

        async def commit(self):
            return None

        async def refresh(self, _value, **_kwargs):
            return None

    async def no_refresh(*_args, **_kwargs):
        return None

    def unexpected_split_assignment(_images):
        raise AssertionError("an immutable snapshot must keep its original splits")

    monkeypatch.setattr(training_operations, "VisionRepository", FakeRepository)
    monkeypatch.setattr(
        training_operations,
        "assign_deterministic_splits",
        unexpected_split_assignment,
    )
    queue = FakeQueue()
    application = VisionApplication(queue=queue)
    application._refresh_dataset = no_refresh
    db = FakeDatabase()

    retry = await application.create_training_run(
        db,
        project.id,
        TrainingRunCreate(dataset_id=dataset.id, preset="fast"),
        SimpleNamespace(id=3, org_id=7),
    )

    assert retry.id == "run-retry"
    assert retry.dataset_id == dataset.id
    assert dataset.status == "locked"
    assert previous_run.status == "failed"
    assert created_runs[0].config["dataset_checksum"] == dataset.manifest_checksum

    created_runs[0].status = "running"
    cancelled = await application.cancel_training_run(
        db,
        created_runs[0].id,
        SimpleNamespace(id=3, org_id=7),
    )
    assert cancelled.status == "cancelling"
    assert queue.revoked == []

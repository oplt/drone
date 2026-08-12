from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from backend.core.database.session import Session
from backend.modules.vision_models.config import vision_settings
from backend.modules.vision_models.models import (
    DatasetImage,
    DatasetVersion,
    ModelVersion,
    TrainingRun,
    VisionModel,
    VisionProject,
)
from backend.modules.vision_models.service.dataset_service import build_yolo_dataset
from backend.modules.vision_models.service.storage import VisionStorage, vision_storage
from backend.modules.vision_models.service.trainers import (
    Trainer,
    TrainerRequest,
    UltralyticsTrainer,
)

logger = logging.getLogger(__name__)


class TrainingCancelled(RuntimeError):
    pass


class TrainingLeaseLost(RuntimeError):
    pass


async def claim_training_run(run_id: str, lease_owner: str) -> int | None:
    now = datetime.now(UTC)
    async with Session() as db:
        result = await db.execute(
            update(TrainingRun)
            .where(TrainingRun.id == run_id, TrainingRun.status == "queued")
            .values(
                status="running",
                attempt=TrainingRun.attempt + 1,
                lease_owner=lease_owner,
                heartbeat_at=now,
                lease_expires_at=now
                + timedelta(seconds=vision_settings.vision_training_lease_seconds),
                started_at=now,
                finished_at=None,
                error=None,
                progress=1.0,
                terminal_reason_code=None,
                terminal_stage=None,
            )
            .returning(TrainingRun.attempt)
            .execution_options(synchronize_session=False)
        )
        attempt = result.scalar_one_or_none()
        await db.commit()
        return int(attempt) if attempt is not None else None


async def training_checkpoint(
    run_id: str,
    *,
    lease_owner: str,
    attempt: int,
    epoch: int,
    total_epochs: int,
    metrics: dict[str, float],
) -> None:
    async with Session() as db:
        run = await db.scalar(
            select(TrainingRun)
            .where(
                TrainingRun.id == run_id,
                TrainingRun.lease_owner == lease_owner,
                TrainingRun.attempt == attempt,
            )
            .with_for_update()
        )
        if run is None:
            raise TrainingLeaseLost("Training lease ownership changed")
        if run.status == "cancelling":
            run.status = "cancelled"
            run.finished_at = datetime.now(UTC)
            run.heartbeat_at = None
            run.lease_expires_at = None
            run.lease_owner = None
            run.terminal_reason_code = "USER_CANCELLED"
            run.terminal_stage = "training"
            await db.commit()
            raise TrainingCancelled("Training was cancelled")
        if run.status != "running":
            raise TrainingLeaseLost("Training run is no longer active")
        now = datetime.now(UTC)
        run.current_epoch = max(run.current_epoch, epoch)
        run.progress = round(min(95.0, epoch / max(1, total_epochs) * 90.0), 2)
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(
            seconds=vision_settings.vision_training_lease_seconds
        )
        if metrics:
            run.metrics = {**run.metrics, "training": metrics}
        await db.commit()


async def heartbeat_training_run(
    run_id: str, *, lease_owner: str, attempt: int
) -> None:
    now = datetime.now(UTC)
    async with Session() as db:
        result = await db.execute(
            update(TrainingRun)
            .where(
                TrainingRun.id == run_id,
                TrainingRun.status.in_(("running", "cancelling")),
                TrainingRun.lease_owner == lease_owner,
                TrainingRun.attempt == attempt,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now
                + timedelta(seconds=vision_settings.vision_training_lease_seconds),
            )
        )
        await db.commit()
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            raise TrainingLeaseLost("Training lease ownership changed")


async def _heartbeat_loop(
    run_id: str, *, lease_owner: str, attempt: int, stopped: asyncio.Event
) -> None:
    while True:
        try:
            await asyncio.wait_for(
                stopped.wait(),
                timeout=vision_settings.vision_training_heartbeat_interval_seconds,
            )
            return
        except TimeoutError:
            await heartbeat_training_run(
                run_id, lease_owner=lease_owner, attempt=attempt
            )


class VisionTrainingService:
    def __init__(
        self,
        *,
        trainer: Trainer | None = None,
        storage: VisionStorage = vision_storage,
    ) -> None:
        self.trainer = trainer or UltralyticsTrainer()
        self.storage = storage

    async def run(
        self, run_id: str, *, lease_owner: str | None = None
    ) -> dict[str, str]:
        owner = lease_owner or str(uuid4())
        attempt = await claim_training_run(run_id, owner)
        if attempt is None:
            async with Session() as db:
                existing = await db.get(TrainingRun, run_id)
                if existing is None:
                    raise ValueError("Training run not found")
                if existing.status == "completed" and existing.model_version is not None:
                    return {
                        "run_id": existing.id,
                        "model_version_id": existing.model_version.id,
                    }
                return {"run_id": existing.id, "status": existing.status}
        try:
            return await self._run(run_id, lease_owner=owner, attempt=attempt)
        except TrainingCancelled:
            return {"run_id": run_id, "status": "cancelled"}
        except Exception as exc:
            async with Session() as db:
                await db.execute(
                    update(TrainingRun)
                    .where(
                        TrainingRun.id == run_id,
                        TrainingRun.status == "running",
                        TrainingRun.lease_owner == owner,
                        TrainingRun.attempt == attempt,
                    )
                    .values(
                        status="failed",
                        error=str(exc)[:4000],
                        finished_at=datetime.now(UTC),
                        lease_owner=None,
                        heartbeat_at=None,
                        lease_expires_at=None,
                        terminal_reason_code="TRAINING_FAILED",
                        terminal_stage="training",
                    )
                )
                await db.commit()
            raise

    async def _run(
        self, run_id: str, *, lease_owner: str, attempt: int
    ) -> dict[str, str]:
        async with Session() as db:
            query = (
                select(TrainingRun)
                .options(
                    selectinload(TrainingRun.project).selectinload(VisionProject.classes),
                    selectinload(TrainingRun.dataset)
                    .selectinload(DatasetVersion.images)
                    .selectinload(DatasetImage.annotations),
                    selectinload(TrainingRun.model_version),
                )
                .where(TrainingRun.id == run_id)
            )
            run = (await db.execute(query)).scalar_one_or_none()
            if run is None:
                raise ValueError("Training run not found")
            if (
                run.status != "running"
                or run.lease_owner != lease_owner
                or run.attempt != attempt
            ):
                return {"run_id": run.id, "status": run.status}

            project = run.project
            dataset = run.dataset
            classes = sorted(project.classes, key=lambda item: item.class_index)
            selected = [image for image in dataset.images if image.selected]
            run_root = self.storage.project_path(project.id, "training", run.id)
            data_root = run_root / "dataset"
            data_config = build_yolo_dataset(
                project_id=project.id,
                dataset=dataset,
                images=selected,
                classes=classes,
                output_dir=data_root,
                storage=self.storage,
            )
            request = TrainerRequest(
                base_model=run.base_model,
                data_config=data_config,
                output_dir=run_root,
                epochs=run.epochs,
                image_size=run.image_size,
                batch_size=run.batch_size,
                requested_device=run.device,
                class_names=[item.name for item in classes],
            )
            loop = asyncio.get_running_loop()

            def progress_callback(epoch: int, total: int, metrics: dict[str, float]) -> None:
                future = asyncio.run_coroutine_threadsafe(
                    training_checkpoint(
                        run.id,
                        lease_owner=lease_owner,
                        attempt=attempt,
                        epoch=epoch,
                        total_epochs=total,
                        metrics=metrics,
                    ),
                    loop,
                )

                future.result(timeout=15)

            try:
                heartbeat_stopped = asyncio.Event()
                heartbeat_task = asyncio.create_task(
                    _heartbeat_loop(
                        run.id,
                        lease_owner=lease_owner,
                        attempt=attempt,
                        stopped=heartbeat_stopped,
                    )
                )
                try:
                    result = await asyncio.to_thread(
                        self.trainer.train, request, progress_callback
                    )
                finally:
                    heartbeat_stopped.set()
                    await heartbeat_task
                await training_checkpoint(
                    run.id,
                    lease_owner=lease_owner,
                    attempt=attempt,
                    epoch=run.epochs,
                    total_epochs=run.epochs,
                    metrics={},
                )
                await db.refresh(run)
                if (
                    run.status != "running"
                    or run.lease_owner != lease_owner
                    or run.attempt != attempt
                ):
                    raise TrainingLeaseLost("Training lease was lost before artifact publish")
                model = await db.scalar(
                    select(VisionModel).where(VisionModel.project_id == project.id)
                )
                if model is None:
                    model = VisionModel(
                        org_id=project.org_id,
                        project_id=project.id,
                        name=project.name,
                        crop=project.crop,
                        task_type=project.task_type,
                    )
                    db.add(model)
                    await db.flush()
                latest_version = await db.scalar(
                    select(func.max(ModelVersion.version)).where(ModelVersion.model_id == model.id)
                )
                version_number = int(latest_version or 0) + 1
                model_root = self.storage.project_path(
                    project.id, "models", model.id, f"v{version_number}"
                )
                model_root.mkdir(parents=True, exist_ok=True)
                weights_path = model_root / "best.pt"
                shutil.copy2(result.best_weights, weights_path)
                checksum = hashlib.sha256(weights_path.read_bytes()).hexdigest()
                artifact_uris: dict[str, str] = {}
                for name, source in result.evaluation_artifacts.items():
                    target = model_root / f"{name}{source.suffix}"
                    shutil.copy2(source, target)
                    artifact_uris[name] = self.storage.to_uri(target)
                metadata = {
                    "training_run_id": run.id,
                    "dataset_id": dataset.id,
                    "dataset_checksum": dataset.manifest_checksum,
                    "base_model": run.base_model,
                    "preset": run.preset,
                    "device": result.device,
                    "classes": [item.name for item in classes],
                    "metrics": result.metrics,
                    "checksum": checksum,
                }
                (model_root / "metadata.json").write_text(
                    json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
                )
                version = ModelVersion(
                    model_id=model.id,
                    training_run_id=run.id,
                    dataset_id=dataset.id,
                    version=version_number,
                    architecture=run.base_model,
                    weights_uri=self.storage.to_uri(weights_path),
                    classes=[item.name for item in classes],
                    metrics=result.metrics,
                    evaluation_artifacts=artifact_uris,
                    checksum=checksum,
                    status="candidate",
                )
                db.add(version)
                run.status = "completed"
                run.progress = 100.0
                run.current_epoch = run.epochs
                run.metrics = result.metrics
                run.device = result.device
                run.finished_at = datetime.now(UTC)
                run.lease_owner = None
                run.heartbeat_at = None
                run.lease_expires_at = None
                run.terminal_reason_code = "COMPLETED"
                run.terminal_stage = "completed"
                await db.commit()
                return {"run_id": run.id, "model_version_id": version.id}
            except Exception:
                await db.rollback()
                logger.exception("Vision training failed run_id=%s", run_id)
                raise


async def reconcile_stale_training_runs(*, limit: int = 100) -> int:
    now = datetime.now(UTC)
    async with Session() as db:
        runs = list(
            (
                await db.scalars(
                    select(TrainingRun)
                    .where(
                        TrainingRun.status.in_(("running", "cancelling")),
                        TrainingRun.lease_expires_at.is_not(None),
                        TrainingRun.lease_expires_at <= now,
                    )
                    .order_by(TrainingRun.lease_expires_at)
                    .with_for_update(skip_locked=True)
                    .limit(max(1, min(limit, 500)))
                )
            ).all()
        )
        for run in runs:
            run.status = "failed"
            run.error = "Training worker heartbeat expired. Start a new training run."
            run.finished_at = now
            run.lease_owner = None
            run.heartbeat_at = None
            run.lease_expires_at = None
            run.terminal_reason_code = "WORKER_LEASE_EXPIRED"
            run.terminal_stage = "worker_lease"
        if runs:
            await db.commit()
        else:
            await db.rollback()
        return len(runs)

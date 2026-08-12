from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.core.database.session import Session
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


async def update_training_progress(
    run_id: str,
    *,
    epoch: int,
    total_epochs: int,
    metrics: dict[str, float],
) -> None:
    async with Session() as db:
        run = await db.get(TrainingRun, run_id)
        if run is None or run.status != "running":
            return
        run.current_epoch = epoch
        run.progress = round(min(95.0, epoch / max(1, total_epochs) * 90.0), 2)
        if metrics:
            run.metrics = {**run.metrics, "training": metrics}
        await db.commit()


class VisionTrainingService:
    def __init__(
        self,
        *,
        trainer: Trainer | None = None,
        storage: VisionStorage = vision_storage,
    ) -> None:
        self.trainer = trainer or UltralyticsTrainer()
        self.storage = storage

    async def run(self, run_id: str) -> dict[str, str]:
        try:
            return await self._run(run_id)
        except Exception as exc:
            async with Session() as db:
                failed = await db.get(TrainingRun, run_id)
                if failed is not None and failed.status not in {"cancelled", "completed"}:
                    failed.status = "failed"
                    failed.error = str(exc)[:4000]
                    failed.finished_at = datetime.now(UTC)
                    await db.commit()
            raise

    async def _run(self, run_id: str) -> dict[str, str]:
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
            if run.status == "completed" and run.model_version is not None:
                return {"run_id": run.id, "model_version_id": run.model_version.id}
            if run.status == "cancelled":
                return {"run_id": run.id, "status": "cancelled"}

            run.status = "running"
            run.started_at = datetime.now(UTC)
            run.finished_at = None
            run.error = None
            run.progress = 1.0
            await db.commit()

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
                    update_training_progress(
                        run.id,
                        epoch=epoch,
                        total_epochs=total,
                        metrics=metrics,
                    ),
                    loop,
                )

                def report_progress_failure(completed) -> None:
                    error = completed.exception()
                    if error is not None:
                        logger.warning(
                            "Training progress update failed run_id=%s error=%s",
                            run.id,
                            error,
                        )

                future.add_done_callback(report_progress_failure)

            try:
                result = await asyncio.to_thread(self.trainer.train, request, progress_callback)
                await db.refresh(run)
                if run.status == "cancelled":
                    return {"run_id": run.id, "status": "cancelled"}
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
                await db.commit()
                return {"run_id": run.id, "model_version_id": version.id}
            except Exception as exc:
                await db.rollback()
                failed = await db.get(TrainingRun, run_id)
                if failed is not None and failed.status != "cancelled":
                    failed.status = "failed"
                    failed.error = str(exc)[:4000]
                    failed.finished_at = datetime.now(UTC)
                    await db.commit()
                logger.exception("Vision training failed run_id=%s", run_id)
                raise

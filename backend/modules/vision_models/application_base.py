from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.vision_models.models import (
    Annotation,
    DatasetImage,
    DatasetVersion,
    ModelVersion,
    TrainingRun,
    VisionModel,
    VisionProject,
)
from backend.modules.vision_models.schemas import (
    DatasetImageOut,
    DatasetOut,
    ModelVersionOut,
    TrainingRunOut,
    VisionProjectOut,
)
from backend.modules.vision_models.service.queue import VisionTrainingQueue
from backend.modules.vision_models.service.storage import VisionStorage, vision_storage

PRESETS = {
    "fast": {"epochs": 25, "image_size": 512, "batch_size": 8},
    "balanced": {"epochs": 50, "image_size": 640, "batch_size": 8},
    "high_accuracy": {"epochs": 100, "image_size": 768, "batch_size": 4},
}


class VisionNotFound(LookupError):
    pass


class VisionConflict(RuntimeError):
    pass


class VisionAnnotationConflict(VisionConflict):
    def __init__(self, *, expected_revision: int, current_revision: int) -> None:
        super().__init__("Annotations changed in another session")
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class VisionValidationError(ValueError):
    pass


class VisionWorkerUnavailable(RuntimeError):
    pass


class VisionApplicationBase:
    def __init__(
        self,
        *,
        storage: VisionStorage = vision_storage,
        queue: VisionTrainingQueue | None = None,
    ) -> None:
        self.storage = storage
        self.queue = queue or VisionTrainingQueue()

    @staticmethod
    def _assert_mutable(dataset: DatasetVersion) -> None:
        if dataset.status == "locked":
            raise VisionConflict("Dataset is locked because it is used by a training run")

    @staticmethod
    def _annotation_payload(annotation: Annotation) -> dict:
        return {
            "id": annotation.id,
            "class_id": annotation.class_id,
            "annotation_type": annotation.annotation_type,
            "x1": annotation.x1,
            "y1": annotation.y1,
            "x2": annotation.x2,
            "y2": annotation.y2,
            "confidence": annotation.confidence,
            "source": annotation.source,
            "created_at": annotation.created_at,
            "updated_at": annotation.updated_at,
        }

    def image_output(self, image: DatasetImage) -> DatasetImageOut:
        return DatasetImageOut(
            id=image.id,
            dataset_id=image.dataset_id,
            content_url=f"/vision/images/{image.id}/content",
            thumbnail_url=f"/vision/images/{image.id}/thumbnail",
            source_type=image.source_type,
            source_video_id=image.source_video_id,
            mission_id=image.mission_id,
            field_id=image.field_id,
            frame_index=image.frame_index,
            timestamp_seconds=image.timestamp_seconds,
            width=image.width,
            height=image.height,
            quality_score=image.quality_score,
            selected=image.selected,
            split=image.split,
            annotation_status=image.annotation_status,
            annotation_revision=image.annotation_revision,
            annotations=[self._annotation_payload(item) for item in image.annotations],
            lat=image.lat,
            lon=image.lon,
            altitude_m=image.altitude_m,
            heading_deg=image.heading_deg,
            metadata=image.metadata_json,
            created_at=image.created_at,
        )

    @staticmethod
    def dataset_output(dataset: DatasetVersion) -> DatasetOut:
        return DatasetOut.model_validate(dataset)

    @staticmethod
    def training_output(run: TrainingRun) -> TrainingRunOut:
        return TrainingRunOut(
            id=run.id,
            project_id=run.project_id,
            dataset_id=run.dataset_id,
            status=run.status,
            trainer=run.trainer,
            base_model=run.base_model,
            preset=run.preset,
            epochs=run.epochs,
            total_epochs=run.epochs,
            image_size=run.image_size,
            batch_size=run.batch_size,
            device=run.device,
            progress=run.progress,
            current_epoch=run.current_epoch,
            metrics=run.metrics,
            error=run.error,
            attempt=getattr(run, "attempt", 0) or 0,
            terminal_reason_code=getattr(run, "terminal_reason_code", None),
            terminal_stage=getattr(run, "terminal_stage", None),
            model_version_id=run.model_version.id if run.model_version else None,
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
        )

    @staticmethod
    def model_output(version: ModelVersion) -> ModelVersionOut:
        return ModelVersionOut(
            id=version.id,
            model_id=version.model_id,
            project_id=version.model.project_id,
            training_run_id=version.training_run_id,
            dataset_id=version.dataset_id,
            name=version.model.name,
            crop=version.model.crop,
            task_type=version.model.task_type,
            capability_id=version.model.project.capability_id,
            version=version.version,
            architecture=version.architecture,
            status=version.status,
            classes=version.classes,
            metrics=version.metrics,
            created_at=version.created_at,
        )

    async def _project_outputs(
        self, db: AsyncSession, projects: list[VisionProject]
    ) -> list[VisionProjectOut]:
        if not projects:
            return []
        ids = [project.id for project in projects]
        datasets = list(
            (
                await db.scalars(
                    select(DatasetVersion)
                    .where(DatasetVersion.project_id.in_(ids))
                    .order_by(DatasetVersion.version.desc())
                )
            ).all()
        )
        versions = list(
            (
                await db.scalars(
                    select(ModelVersion)
                    .join(VisionModel)
                    .where(VisionModel.project_id.in_(ids))
                    .order_by(ModelVersion.version.desc())
                )
            ).all()
        )
        datasets_by_project: dict[str, list[DatasetVersion]] = {}
        for dataset in datasets:
            datasets_by_project.setdefault(dataset.project_id, []).append(dataset)
        versions_by_project: dict[str, list[ModelVersion]] = {}
        model_project = dict(
            (
                await db.execute(
                    select(VisionModel.id, VisionModel.project_id).where(
                        VisionModel.project_id.in_(ids)
                    )
                )
            ).all()
        )
        for version in versions:
            project_id = model_project.get(version.model_id)
            if project_id:
                versions_by_project.setdefault(project_id, []).append(version)
        output = []
        for project in projects:
            project_datasets = datasets_by_project.get(project.id, [])
            project_versions = versions_by_project.get(project.id, [])
            production = next(
                (item.version for item in project_versions if item.status == "production"),
                None,
            )
            output.append(
                VisionProjectOut(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    crop=project.crop,
                    task_type=project.task_type,
                    capability_id=project.capability_id,
                    status=project.status,
                    classes=project.classes,
                    dataset_count=len(project_datasets),
                    latest_dataset_status=(
                        project_datasets[0].status if project_datasets else None
                    ),
                    latest_model_version=(
                        project_versions[0].version if project_versions else None
                    ),
                    production_model_version=production,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                )
            )
        return output

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.identity.models import User
from backend.modules.vision_models.application_base import (
    VisionConflict,
    VisionNotFound,
)
from backend.modules.vision_models.models import (
    Annotation,
    DatasetImage,
    DatasetVersion,
    TrainingRun,
    VisionClass,
    VisionProject,
)
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.vision_models.schemas import (
    DatasetOut,
    VisionProjectCreate,
    VisionProjectOut,
    VisionProjectPatch,
)


class ProjectOperations:
    async def create_project(
        self, db: AsyncSession, payload: VisionProjectCreate, user: User
    ) -> VisionProjectOut:
        project = VisionProject(
            org_id=user.org_id,
            name=payload.name,
            description=payload.description,
            crop=payload.crop,
            task_type=payload.task_type,
            capability_id=payload.capability_id,
            status="draft",
            created_by_user_id=user.id,
            classes=[
                VisionClass(name=item.name, class_index=index)
                for index, item in enumerate(payload.classes)
            ],
        )
        db.add(project)
        await db.commit()
        project = await VisionRepository(db).get_project(project.id, user)
        if project is None:
            raise VisionNotFound("Vision project not found after creation")
        return (await self._project_outputs(db, [project]))[0]

    async def list_projects(self, db: AsyncSession, user: User) -> list[VisionProjectOut]:
        projects = await VisionRepository(db).list_projects(user)
        return await self._project_outputs(db, projects)

    async def get_project(
        self, db: AsyncSession, project_id: str, user: User
    ) -> VisionProjectOut:
        project = await VisionRepository(db).get_project(project_id, user)
        if project is None:
            raise VisionNotFound("Vision project not found")
        return (await self._project_outputs(db, [project]))[0]

    async def patch_project(
        self,
        db: AsyncSession,
        project_id: str,
        payload: VisionProjectPatch,
        user: User,
    ) -> VisionProjectOut:
        repo = VisionRepository(db)
        project = await repo.get_project(project_id, user)
        if project is None:
            raise VisionNotFound("Vision project not found")
        if payload.classes is not None:
            dataset_exists = await db.scalar(
                select(func.count())
                .select_from(DatasetVersion)
                .where(DatasetVersion.project_id == project.id)
            )
            if dataset_exists:
                raise VisionConflict("Classes cannot change after the first dataset is created")
            project.classes.clear()
            project.classes.extend(
                VisionClass(name=item.name, class_index=index)
                for index, item in enumerate(payload.classes)
            )
        if payload.name is not None:
            project.name = payload.name.strip()
        if payload.crop is not None:
            project.crop = payload.crop.strip()
        if "description" in payload.model_fields_set:
            project.description = payload.description
        await db.commit()
        refreshed = await repo.get_project(project.id, user)
        if refreshed is None:
            raise VisionNotFound("Vision project not found")
        return (await self._project_outputs(db, [refreshed]))[0]

    async def delete_project(self, db: AsyncSession, project_id: str, user: User) -> None:
        repo = VisionRepository(db)
        project = await repo.get_project(project_id, user)
        if project is None:
            raise VisionNotFound("Vision project not found")
        training_count = await db.scalar(
            select(func.count())
            .select_from(TrainingRun)
            .where(TrainingRun.project_id == project.id)
        )
        if training_count:
            raise VisionConflict("Projects with training history cannot be deleted")
        await db.delete(project)
        await db.commit()
        await run_blocking(
            self.storage.remove_project,
            project_id,
            boundary="filesystem",
            operation="delete_vision_project_storage",
            timeout_s=60,
        )

    async def create_dataset(
        self,
        db: AsyncSession,
        project_id: str,
        user: User,
        *,
        clone_from_dataset_id: str | None = None,
    ) -> DatasetOut:
        repo = VisionRepository(db)
        project = await repo.get_project(project_id, user)
        if project is None:
            raise VisionNotFound("Vision project not found")
        source = None
        if clone_from_dataset_id:
            source = await repo.get_dataset(clone_from_dataset_id, user)
            if source is None or source.project_id != project.id:
                raise VisionNotFound("Source dataset not found")
        latest = await db.scalar(
            select(func.max(DatasetVersion.version)).where(
                DatasetVersion.project_id == project.id
            )
        )
        dataset = DatasetVersion(project_id=project.id, version=int(latest or 0) + 1)
        db.add(dataset)
        await db.flush()
        if source is not None:
            source_images = await repo.all_dataset_images(source.id)
            for source_image in source_images:
                clone = DatasetImage(
                    dataset_id=dataset.id,
                    storage_uri=source_image.storage_uri,
                    thumbnail_uri=source_image.thumbnail_uri,
                    source_type=source_image.source_type,
                    source_group=source_image.source_group,
                    source_video_id=source_image.source_video_id,
                    mission_id=source_image.mission_id,
                    field_id=source_image.field_id,
                    frame_index=source_image.frame_index,
                    timestamp_seconds=source_image.timestamp_seconds,
                    width=source_image.width,
                    height=source_image.height,
                    sha256=source_image.sha256,
                    perceptual_hash=source_image.perceptual_hash,
                    quality_score=source_image.quality_score,
                    selected=source_image.selected,
                    split=None,
                    annotation_status=source_image.annotation_status,
                    annotation_revision=0,
                    lat=source_image.lat,
                    lon=source_image.lon,
                    altitude_m=source_image.altitude_m,
                    heading_deg=source_image.heading_deg,
                    metadata_json={
                        **(source_image.metadata_json or {}),
                        "cloned_from_dataset_id": source.id,
                        "cloned_from_image_id": source_image.id,
                    },
                )
                clone.annotations = [
                    Annotation(
                        annotation_type=item.annotation_type,
                        class_id=item.class_id,
                        x1=item.x1,
                        y1=item.y1,
                        x2=item.x2,
                        y2=item.y2,
                        confidence=item.confidence,
                        source=item.source,
                        created_by_user_id=user.id,
                    )
                    for item in source_image.annotations
                ]
                db.add(clone)
            await self._refresh_dataset(db, dataset)
        await db.commit()
        await db.refresh(dataset)
        return self.dataset_output(dataset)

    async def list_datasets(
        self, db: AsyncSession, project_id: str, user: User
    ) -> list[DatasetOut]:
        if await VisionRepository(db).get_project(project_id, user) is None:
            raise VisionNotFound("Vision project not found")
        return [
            self.dataset_output(item)
            for item in await VisionRepository(db).list_datasets(project_id, user)
        ]

    async def get_dataset(
        self, db: AsyncSession, dataset_id: str, user: User
    ) -> DatasetOut:
        dataset = await VisionRepository(db).get_dataset(dataset_id, user)
        if dataset is None:
            raise VisionNotFound("Dataset not found")
        return self.dataset_output(dataset)

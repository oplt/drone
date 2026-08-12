from __future__ import annotations

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.modules.identity.models import User
from backend.modules.vision_models.models import (
    DatasetImage,
    DatasetVersion,
    ModelVersion,
    TrainingRun,
    VisionModel,
    VisionProject,
)


class VisionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def project_visible_to(user: User):
        if user.org_id is not None:
            return VisionProject.org_id == user.org_id
        return VisionProject.created_by_user_id == user.id

    @staticmethod
    def project_visible_to_scope(org_id: int | None, user_id: int | None = None):
        if org_id is not None:
            return VisionProject.org_id == org_id
        return VisionProject.created_by_user_id == user_id

    def project_query(self, user: User) -> Select[tuple[VisionProject]]:
        return (
            select(VisionProject)
            .options(selectinload(VisionProject.classes))
            .where(self.project_visible_to(user))
        )

    async def list_projects(self, user: User) -> list[VisionProject]:
        result = await self.db.scalars(
            self.project_query(user).order_by(VisionProject.updated_at.desc())
        )
        return list(result.unique().all())

    async def get_project(self, project_id: str, user: User) -> VisionProject | None:
        result = await self.db.execute(
            self.project_query(user).where(VisionProject.id == project_id)
        )
        return result.unique().scalar_one_or_none()

    async def get_dataset(self, dataset_id: str, user: User) -> DatasetVersion | None:
        result = await self.db.execute(
            select(DatasetVersion)
            .join(VisionProject)
            .options(selectinload(DatasetVersion.project))
            .where(
                DatasetVersion.id == dataset_id,
                self.project_visible_to(user),
            )
        )
        return result.scalar_one_or_none()

    async def list_datasets(self, project_id: str, user: User) -> list[DatasetVersion]:
        result = await self.db.scalars(
            select(DatasetVersion)
            .join(VisionProject)
            .where(
                DatasetVersion.project_id == project_id,
                self.project_visible_to(user),
            )
            .order_by(DatasetVersion.version.desc())
        )
        return list(result.all())

    async def list_images(
        self,
        dataset_id: str,
        user: User,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DatasetImage]:
        result = await self.db.execute(
            select(DatasetImage)
            .join(DatasetVersion)
            .join(VisionProject)
            .options(selectinload(DatasetImage.annotations))
            .where(
                DatasetImage.dataset_id == dataset_id,
                self.project_visible_to(user),
            )
            .order_by(DatasetImage.created_at, DatasetImage.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.unique().scalars().all())

    async def get_image(self, image_id: str, user: User) -> DatasetImage | None:
        result = await self.db.execute(
            select(DatasetImage)
            .join(DatasetVersion)
            .join(VisionProject)
            .options(
                selectinload(DatasetImage.annotations),
                selectinload(DatasetImage.dataset).selectinload(DatasetVersion.project),
            )
            .where(DatasetImage.id == image_id, self.project_visible_to(user))
        )
        return result.unique().scalar_one_or_none()

    async def claim_annotation_revision(
        self, image_id: str, *, expected_revision: int
    ) -> int | None:
        result = await self.db.execute(
            update(DatasetImage)
            .where(
                DatasetImage.id == image_id,
                DatasetImage.annotation_revision == expected_revision,
            )
            .values(annotation_revision=DatasetImage.annotation_revision + 1)
            .returning(DatasetImage.annotation_revision)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none()

    async def all_dataset_images(self, dataset_id: str) -> list[DatasetImage]:
        result = await self.db.execute(
            select(DatasetImage)
            .options(selectinload(DatasetImage.annotations))
            .where(DatasetImage.dataset_id == dataset_id)
            .order_by(DatasetImage.created_at, DatasetImage.id)
        )
        return list(result.unique().scalars().all())

    async def get_training_run(self, run_id: str, user: User) -> TrainingRun | None:
        result = await self.db.execute(
            select(TrainingRun)
            .join(VisionProject)
            .options(selectinload(TrainingRun.model_version))
            .where(TrainingRun.id == run_id, self.project_visible_to(user))
        )
        return result.unique().scalar_one_or_none()

    async def list_training_runs(self, project_id: str, user: User) -> list[TrainingRun]:
        result = await self.db.scalars(
            select(TrainingRun)
            .join(VisionProject)
            .where(
                TrainingRun.project_id == project_id,
                self.project_visible_to(user),
            )
            .order_by(TrainingRun.created_at.desc())
        )
        return list(result.all())

    async def get_model_version(
        self,
        version_id: str,
        user: User,
        *,
        for_update: bool = False,
    ) -> ModelVersion | None:
        query = (
            select(ModelVersion)
            .join(VisionModel)
            .join(VisionProject)
            .options(
                selectinload(ModelVersion.model).selectinload(VisionModel.project),
                selectinload(ModelVersion.training_run),
            )
            .where(ModelVersion.id == version_id, self.project_visible_to(user))
        )
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.unique().scalar_one_or_none()

    async def get_model_version_for_scope(
        self,
        version_id: str,
        *,
        org_id: int | None,
        user_id: int | None = None,
    ) -> ModelVersion | None:
        result = await self.db.execute(
            select(ModelVersion)
            .join(VisionModel)
            .join(VisionProject)
            .options(
                selectinload(ModelVersion.model).selectinload(VisionModel.project)
            )
            .where(
                ModelVersion.id == version_id,
                self.project_visible_to_scope(org_id, user_id),
            )
        )
        return result.unique().scalar_one_or_none()

    async def list_model_versions(self, user: User) -> list[ModelVersion]:
        result = await self.db.execute(
            select(ModelVersion)
            .join(VisionModel)
            .join(VisionProject)
            .options(
                selectinload(ModelVersion.model).selectinload(VisionModel.project),
                selectinload(ModelVersion.training_run),
            )
            .where(self.project_visible_to(user))
            .order_by(VisionModel.name, ModelVersion.version.desc())
        )
        return list(result.unique().scalars().all())

    async def list_versions_for_model(self, model_id: str, user: User) -> list[ModelVersion]:
        result = await self.db.execute(
            select(ModelVersion)
            .join(VisionModel)
            .join(VisionProject)
            .options(
                selectinload(ModelVersion.model).selectinload(VisionModel.project),
                selectinload(ModelVersion.training_run),
            )
            .where(VisionModel.id == model_id, self.project_visible_to(user))
            .order_by(ModelVersion.version.desc())
        )
        return list(result.unique().scalars().all())

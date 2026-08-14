from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.runtime.blocking import run_blocking
from backend.modules.identity.models import User
from backend.modules.vision_models.application_base import (
    VisionAnnotationConflict,
    VisionNotFound,
    VisionValidationError,
)
from backend.modules.vision_models.models import Annotation, DatasetImage, VisionClass
from backend.modules.vision_models.repository import VisionRepository
from backend.modules.vision_models.schemas import (
    AnnotationReplace,
    DatasetImageOut,
)
from backend.modules.vision_models.service.dataset_service import (
    DatasetServiceError,
    build_yolo_export,
    parse_yolo_annotation_zip,
)
from backend.modules.vision_models.service.storage import VisionStorageError


class AnnotationOperations:
    async def list_images(
        self,
        db: AsyncSession,
        dataset_id: str,
        user: User,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[DatasetImageOut], int]:
        repo = VisionRepository(db)
        if await repo.get_dataset(dataset_id, user) is None:
            raise VisionNotFound("Dataset not found")
        total = int(
            await db.scalar(
                select(func.count())
                .select_from(DatasetImage)
                .where(DatasetImage.dataset_id == dataset_id)
            )
            or 0
        )
        images = await repo.list_images(dataset_id, user, offset=offset, limit=limit)
        return [self.image_output(image) for image in images], total

    async def resolve_image_media(
        self, db: AsyncSession, image_id: str, user: User, *, thumbnail: bool
    ) -> Path:
        image = await VisionRepository(db).get_image(image_id, user)
        if image is None:
            raise VisionNotFound("Dataset image not found")
        uri = image.thumbnail_uri if thumbnail else image.storage_uri
        storage_object = (
            image.thumbnail_storage_object if thumbnail else image.storage_object
        )
        if not uri and storage_object is None:
            raise VisionNotFound("Image artifact is unavailable")
        try:
            path = self.storage.resolve_registered(
                backend_key=(
                    storage_object.backend_key if storage_object is not None else None
                ),
                legacy_uri=uri,
            )
        except VisionStorageError as exc:
            raise VisionNotFound("Image artifact is unavailable") from exc
        if not path.is_file():
            raise VisionNotFound("Image artifact is unavailable")
        return path

    async def replace_annotations(
        self,
        db: AsyncSession,
        image_id: str,
        payload: AnnotationReplace,
        user: User,
    ) -> DatasetImageOut:
        repo = VisionRepository(db)
        image = await repo.get_image(image_id, user)
        if image is None:
            raise VisionNotFound("Dataset image not found")
        self._assert_mutable(image.dataset)
        class_ids = set(
            (
                await db.scalars(
                    select(VisionClass.id).where(
                        VisionClass.project_id == image.dataset.project_id
                    )
                )
            ).all()
        )
        if any(item.class_id not in class_ids for item in payload.annotations):
            raise VisionValidationError("Annotation class does not belong to this project")
        if any(
            item.x2 > image.width or item.y2 > image.height
            for item in payload.annotations
        ):
            raise VisionValidationError(
                "Annotation coordinates must stay within the original image bounds"
            )
        claimed_revision = await repo.claim_annotation_revision(
            image.id, expected_revision=payload.expected_revision
        )
        if claimed_revision is None:
            await db.rollback()
            current = await repo.get_image(image_id, user)
            raise VisionAnnotationConflict(
                expected_revision=payload.expected_revision,
                current_revision=current.annotation_revision if current is not None else -1,
            )
        image.annotation_revision = claimed_revision
        image.annotations.clear()
        image.annotations.extend(
            Annotation(
                image_id=image.id,
                class_id=item.class_id,
                x1=item.x1,
                y1=item.y1,
                x2=item.x2,
                y2=item.y2,
                confidence=item.confidence,
                source=item.source,
                created_by_user_id=user.id,
            )
            for item in payload.annotations
        )
        image.annotation_status = (
            "reviewed"
            if payload.reviewed
            else "labeled"
            if payload.annotations
            else "unlabeled"
        )
        await self._refresh_dataset(db, image.dataset)
        await db.commit()
        refreshed = await repo.get_image(image.id, user)
        if refreshed is None:
            raise VisionNotFound("Dataset image not found")
        return self.image_output(refreshed)

    async def set_image_selected(
        self, db: AsyncSession, image_id: str, selected: bool, user: User
    ) -> DatasetImageOut:
        repo = VisionRepository(db)
        image = await repo.get_image(image_id, user)
        if image is None:
            raise VisionNotFound("Dataset image not found")
        self._assert_mutable(image.dataset)
        image.selected = selected
        await self._refresh_dataset(db, image.dataset)
        await db.commit()
        refreshed = await repo.get_image(image.id, user)
        if refreshed is None:
            raise VisionNotFound("Dataset image not found")
        return self.image_output(refreshed)

    async def import_yolo_annotations(
        self, db: AsyncSession, dataset_id: str, content: bytes, user: User
    ) -> dict[str, int]:
        repo = VisionRepository(db)
        dataset = await repo.get_dataset(dataset_id, user)
        if dataset is None:
            raise VisionNotFound("Dataset not found")
        self._assert_mutable(dataset)
        images = await repo.all_dataset_images(dataset.id)
        class_ids = list(
            (
                await db.scalars(
                    select(VisionClass.id)
                    .where(VisionClass.project_id == dataset.project_id)
                    .order_by(VisionClass.class_index)
                )
            ).all()
        )
        try:
            parsed = parse_yolo_annotation_zip(
                content,
                image_ids={item.id for item in images},
                class_ids=class_ids,
            )
        except DatasetServiceError as exc:
            raise VisionValidationError(str(exc)) from exc
        by_id = {item.id: item for item in images}
        imported = 0
        for image_id, rows in parsed.items():
            image = by_id[image_id]
            image.annotation_revision += 1
            image.annotations.clear()
            for class_id, x1, y1, x2, y2 in rows:
                image.annotations.append(
                    Annotation(
                        image_id=image.id,
                        class_id=class_id,
                        x1=x1 * image.width,
                        y1=y1 * image.height,
                        x2=x2 * image.width,
                        y2=y2 * image.height,
                        source="imported",
                        created_by_user_id=user.id,
                    )
                )
                imported += 1
            image.annotation_status = "labeled"
        await self._refresh_dataset(db, dataset)
        await db.commit()
        return {"images_updated": len(parsed), "annotations_imported": imported}

    async def export_yolo_dataset(
        self, db: AsyncSession, dataset_id: str, user: User
    ) -> tuple[Path, str]:
        repo = VisionRepository(db)
        dataset = await repo.get_dataset(dataset_id, user)
        if dataset is None:
            raise VisionNotFound("Dataset not found")
        images = await repo.all_dataset_images(dataset.id)
        classes = list(
            (
                await db.scalars(
                    select(VisionClass)
                    .where(VisionClass.project_id == dataset.project_id)
                    .order_by(VisionClass.class_index)
                )
            ).all()
        )
        try:
            archive = await run_blocking(
                build_yolo_export,
                project_id=dataset.project_id,
                dataset=dataset,
                images=images,
                classes=classes,
                storage=self.storage,
                boundary="filesystem",
                operation="export_yolo_dataset",
                timeout_s=300,
            )
        except DatasetServiceError as exc:
            raise VisionValidationError(str(exc)) from exc
        return archive, f"vision-dataset-v{dataset.version}.zip"

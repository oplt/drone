from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.modules.vision_models.contracts import VisionModelRelease
from backend.modules.vision_models.models import ModelVersion, VisionModel, VisionProject


def model_release_from_orm(version: ModelVersion) -> VisionModelRelease:
    model = version.model
    project = model.project
    return VisionModelRelease(
        version_id=version.id,
        status=version.status,
        model_id=model.id,
        model_name=model.name,
        model_version=version.version,
        model_checksum=version.checksum,
        dataset_id=version.dataset_id,
        crop=model.crop,
        classes=tuple(version.classes or ()),
        evaluation_metrics=dict(version.metrics or {}),
        capability_id=project.capability_id,
        project_org_id=project.org_id,
        project_created_by_user_id=project.created_by_user_id,
    )


async def list_production_model_releases(
    db: AsyncSession, *, version_ids: Iterable[str]
) -> dict[str, VisionModelRelease]:
    ids = sorted(set(version_ids))
    if not ids:
        return {}
    rows = (
        await db.scalars(
            select(ModelVersion)
            .join(VisionModel)
            .join(VisionProject)
            .options(
                selectinload(ModelVersion.model).selectinload(VisionModel.project)
            )
            .where(
                ModelVersion.id.in_(ids),
                ModelVersion.status == "production",
            )
        )
    ).all()
    return {row.id: model_release_from_orm(row) for row in rows}

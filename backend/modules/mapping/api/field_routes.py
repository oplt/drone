from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database.session import get_db
from backend.modules.identity.dependencies import OrgUser, require_org_user
from backend.modules.mapping.api.mapping_route_schemas import (
    FieldModelVersionOut,
    FieldRegistryOut,
    MappingJobStatusOut,
)
from backend.modules.mapping.api.mapping_route_support import (
    get_owned_field_or_404,
    to_job_status,
)
from backend.modules.mapping.application import mapping_application

router = APIRouter(tags=["mapping"])


@router.get("/fields/{field_id}/latest-ready", response_model=MappingJobStatusOut)
async def get_latest_ready_mapping_for_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> MappingJobStatusOut:
    field = await get_owned_field_or_404(db, field_id=field_id, user=org_user.user)
    latest = await mapping_application.latest_ready(db, field_id=field.id)
    if not latest:
        raise HTTPException(status_code=404, detail="No ready mapping model for this field")
    job, assets = latest
    return to_job_status(job, assets)


@router.get("/fields/{field_id}/models", response_model=list[FieldModelVersionOut])
async def list_field_model_versions(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> list[FieldModelVersionOut]:
    field = await get_owned_field_or_404(db, field_id=field_id, user=org_user.user)
    versions = await mapping_application.list_versions(db, field_id=field.id)
    return [
        FieldModelVersionOut(
            id=version.id,
            version=version.version,
            status=version.status,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.get("/fields/{field_id}/registry", response_model=FieldRegistryOut)
async def get_field_registry(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    org_user: OrgUser = Depends(require_org_user),
) -> FieldRegistryOut:
    user = org_user.user
    field = await get_owned_field_or_404(db, field_id=field_id, user=user)
    versions = await mapping_application.list_versions(db, field_id=field.id)
    return FieldRegistryOut(
        field_id=field.id,
        field_name=field.name,
        owner_id=int(field.owner_id or user.id),
        coordinate_system="EPSG:4326",
        versions=[
            FieldModelVersionOut(
                id=version.id,
                version=version.version,
                status=version.status,
                created_at=version.created_at,
            )
            for version in versions
        ],
    )
